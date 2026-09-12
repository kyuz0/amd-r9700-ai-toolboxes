#!/usr/bin/env python3
"""CPU-only check of Torch's separately executed file-system SHM manager."""

import json
import pathlib
import subprocess
import time

import torch
import torch.multiprocessing as mp


def receiver(storage: torch.Tensor) -> None:
    assert storage.device.type == "cpu"
    assert storage.is_shared()
    assert storage.tolist() == [0, 1, 2, 3]
    storage.add_(10)


def main() -> None:
    started = time.monotonic()
    manager = pathlib.Path(torch.__file__).parent / "bin" / "torch_shm_manager"
    linked = subprocess.run(
        ["ldd", str(manager)], text=True, capture_output=True, timeout=10, check=True
    )
    if "not found" in linked.stdout:
        raise RuntimeError(linked.stdout)
    mp.set_sharing_strategy("file_system")
    storage = torch.arange(4, dtype=torch.int64).share_memory_()
    child = mp.get_context("spawn").Process(target=receiver, args=(storage,))
    child.start()
    child.join(timeout=20)
    if child.is_alive():
        child.terminate()
        child.join(timeout=5)
        raise TimeoutError("CPU shared-storage receiver did not finish in 20 seconds")
    assert child.exitcode == 0, child.exitcode
    assert storage.tolist() == [10, 11, 12, 13], storage
    print(json.dumps({
        "result": "pass",
        "sharing_strategy": mp.get_sharing_strategy(),
        "torch": torch.__version__,
        "manager": str(manager),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }), flush=True)


if __name__ == "__main__":
    main()
