#!/usr/bin/env python3
"""Bounded two-R9700 prerequisite checks, usable on either ROCm stack.

Run under an external process/container timeout as documented in README.md.
Does not load models, alter host settings, or estimate inference performance.
"""
import argparse
import ctypes
import datetime
import gc
import json
import os
import resource
import sys
import tempfile
import time
import traceback


def mapped_host_test(torch, device):
    """Check HIP mapped-host allocation and an actual device write into it."""
    hip = ctypes.CDLL("libamdhip64.so")
    hip.hipHostMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t, ctypes.c_uint]
    hip.hipHostGetDevicePointer.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint]
    hip.hipMemset.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t]
    hip.hipHostFree.argtypes = [ctypes.c_void_p]

    def check(name, *args):
        rc = getattr(hip, name)(*args)
        if rc:
            raise RuntimeError(f"{name} returned HIP error {rc}")

    pointer = ctypes.c_void_p()
    mapped = ctypes.c_void_p()
    size = 1024 * 1024
    check("hipHostMalloc", ctypes.byref(pointer), size, 2)  # hipHostMallocMapped
    try:
        check("hipHostGetDevicePointer", ctypes.byref(mapped), pointer, 0)
        check("hipMemset", mapped, 37, size)
        torch.cuda.synchronize(device)
        assert ctypes.c_uint8.from_address(pointer.value).value == 37
        assert ctypes.c_uint8.from_address(pointer.value + size - 1).value == 37
    finally:
        check("hipHostFree", pointer)
    return {"bytes": size, "device_write_visible_on_host": True}


def worker(rank, init_file, outbound, inbound, barrier, result_queue):
    import torch
    import torch.distributed as dist

    report = {"rank": rank, "status": "failed"}

    def stage(name):
        report["last_stage"] = name
        print(json.dumps({"rank": rank, "stage": name,
                          "monotonic_seconds": time.monotonic()}),
              file=sys.stderr, flush=True)

    try:
        stage("device_init")
        torch.cuda.set_device(rank)
        prop = torch.cuda.get_device_properties(rank)
        arch = prop.gcnArchName.split(":", 1)[0]
        assert arch == "gfx1201", f"Expected gfx1201, got {arch}"
        assert "R9700" in prop.name, f"Expected R9700, got {prop.name}"
        report.update(name=prop.name, arch=arch, total_vram_bytes=prop.total_memory)

        stage("matmul")
        a = torch.ones((128, 128), dtype=torch.float32, device=rank)
        b = a @ a
        assert torch.all(b == 128).item()
        report["matmul"] = "pass"

        stage("local_graph")
        x = torch.zeros(4096, device=rank)
        stream = torch.cuda.Stream(device=rank)
        stream.wait_stream(torch.cuda.current_stream(rank))
        with torch.cuda.stream(stream):
            x.add_(1)
        torch.cuda.current_stream(rank).wait_stream(stream)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph, stream=stream):
            x.add_(1)
        for _ in range(3):
            graph.replay()
        torch.cuda.synchronize(rank)
        # Capture records the add but does not execute it.
        assert torch.all(x == 4).item(), x[0].item()
        report["local_graph_replay"] = "pass"

        stage("pinned_host")
        pinned_results = []
        for mib in (1, 8, 64):
            host = torch.full((mib * 1024**2,), 13, dtype=torch.uint8, pin_memory=True)
            gpu = host.to(rank, non_blocking=True)
            torch.cuda.synchronize(rank)
            assert gpu[0].item() == 13 and gpu[-1].item() == 13
            pinned_results.append({"mib": mib, "pinned": host.is_pinned()})
            del host, gpu
        report["pinned_host_allocations"] = pinned_results
        stage("mapped_host")
        report["mapped_host"] = mapped_host_test(torch, rank)

        # torch multiprocessing transports GPU storage through HIP IPC. Keep
        # both owners alive until the other rank has finished device reads.
        stage("bidirectional_hip_ipc")
        owned = torch.full((4096,), rank + 11, device=rank, dtype=torch.float32)
        outbound.put(owned)
        imported = inbound.get(timeout=40)
        copied = imported.to(rank)
        torch.cuda.synchronize(rank)
        assert torch.all(copied == (1 - rank) + 11).item()
        barrier.wait(timeout=40)
        del copied, imported
        barrier.wait(timeout=40)
        # The receiving processes have released their imported storage. Finish
        # each producer's feeder before releasing the owner and queue handles;
        # otherwise multiprocessing cleanup can retain HIP IPC allocations.
        outbound.close()
        outbound.join_thread()
        inbound.close()
        del owned
        gc.collect()
        report["bidirectional_hip_ipc"] = "pass"
        report["peer_access"] = torch.cuda.can_device_access_peer(rank, 1 - rank)

        # PyTorch calls this backend 'nccl' on ROCm; its implementation is RCCL.
        stage("rccl_init")
        dist.init_process_group("nccl", init_method="file://" + init_file,
                                rank=rank, world_size=2,
                                device_id=torch.device("cuda", rank),
                                timeout=datetime.timedelta(seconds=40))
        for dtype in (torch.float32, torch.float16, torch.bfloat16):
            stage("rccl_allreduce_" + str(dtype))
            value = torch.full((8192,), rank + 1, device=rank, dtype=dtype)
            dist.all_reduce(value)
            torch.cuda.synchronize(rank)
            assert torch.all(value == 3).item(), str(dtype)
        report["rccl_all_reduce_dtypes"] = ["float32", "float16", "bfloat16"]

        stage("rccl_graph_warmup")
        value = torch.full((8192,), rank + 1, device=rank, dtype=torch.bfloat16)
        comm_stream = torch.cuda.Stream(device=rank)
        comm_stream.wait_stream(torch.cuda.current_stream(rank))
        with torch.cuda.stream(comm_stream):
            for _ in range(3):
                value.fill_(rank + 1)
                dist.all_reduce(value)
        torch.cuda.current_stream(rank).wait_stream(comm_stream)
        torch.cuda.synchronize(rank)
        dist.barrier(device_ids=[rank])
        stage("rccl_graph_capture")
        comm_graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(comm_graph, stream=comm_stream):
            value.fill_(rank + 1)
            dist.all_reduce(value)
        stage("rccl_graph_replay")
        for _ in range(3):
            comm_graph.replay()
        torch.cuda.synchronize(rank)
        assert torch.all(value == 3).item()
        report["rccl_graph_replay_bfloat16"] = "pass"

        # Captured RCCL nodes retain references to the communicator. Releasing
        # the process group while that executable graph is alive can deadlock
        # ncclCommDestroy, even after every replay has completed successfully.
        # Related PyTorch lifecycle issue: pytorch/pytorch#115388.
        # Both ranks finish their replays before either releases graph state.
        stage("rccl_graph_release")
        barrier.wait(timeout=40)
        comm_graph.reset()
        graph.reset()
        del comm_graph, graph, value, comm_stream, stream
        gc.collect()
        torch.cuda.synchronize(rank)
        barrier.wait(timeout=40)
        stage("rccl_destroy")
        dist.destroy_process_group()
        report["status"] = "passed"
        stage("complete")
    except BaseException:
        report["error"] = traceback.format_exc()
    finally:
        result_queue.put(report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()
    import torch
    import torch.multiprocessing as mp

    started = time.monotonic()
    report = {
        "schema_version": 1, "torch": torch.__version__, "hip": torch.version.hip,
        "visible_device_count": torch.cuda.device_count(),
        "memlock_bytes": resource.getrlimit(resource.RLIMIT_MEMLOCK),
        "environment": {key: os.environ.get(key) for key in (
            "ROCR_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES",
            "NCCL_P2P_DISABLE", "NCCL_SHM_DISABLE", "NCCL_ALGO", "NCCL_PROTO",
            "HSA_OVERRIDE_GFX_VERSION")},
    }
    if report["visible_device_count"] != 2:
        raise RuntimeError("Expose exactly the two R9700s; exclude the iGPU")
    if report["environment"]["HSA_OVERRIDE_GFX_VERSION"]:
        raise RuntimeError("Probe requires actual gfx1201 detection, without an architecture override")
    ctx = mp.get_context("spawn")
    q0, q1, results = ctx.Queue(), ctx.Queue(), ctx.Queue()
    barrier = ctx.Barrier(2)
    with tempfile.TemporaryDirectory(prefix="r9v-probe-") as temp:
        init_file = os.path.join(temp, "rccl-init")
        processes = [ctx.Process(target=worker, args=(rank, init_file,
                     q0 if rank == 0 else q1, q1 if rank == 0 else q0,
                     barrier, results)) for rank in (0, 1)]
        for process in processes:
            process.start()
        deadline = time.monotonic() + args.timeout_seconds
        rank_results = []
        try:
            while len(rank_results) < 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Runtime probe deadline exceeded")
                rank_results.append(results.get(timeout=remaining))
        except BaseException:
            report["supervisor_error"] = traceback.format_exc()
        finally:
            for process in processes:
                process.join(timeout=2)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
        report["ranks"] = sorted(rank_results, key=lambda row: row["rank"])
        report["process_exit_codes"] = [process.exitcode for process in processes]
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["status"] = "passed" if (len(rank_results) == 2 and
        all(row["status"] == "passed" for row in rank_results) and
        report["process_exit_codes"] == [0, 0]) else "failed"
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
