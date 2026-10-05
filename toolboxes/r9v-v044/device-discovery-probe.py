#!/usr/bin/env python3
"""Check AMD SMI identity without GPUs; optionally verify actual R9700 discovery.

Torch must be imported first to reproduce the published-image startup failure.
Use --gpu with ROCR_VISIBLE_DEVICES selecting the two R9700s on a GPU host.
"""
import argparse
import ctypes
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()

    import torch
    from amdsmi import amdsmi_wrapper

    root = Path(torch.__file__).resolve().parent.parent
    core = root / "_rocm_sdk_core/lib/libamd_smi.so.27"
    native = ctypes.CDLL(str(core))
    binding = amdsmi_wrapper._libraries["libamd_smi.so"]
    native_init = ctypes.cast(native.amdsmi_init, ctypes.c_void_p).value
    binding_init = ctypes.cast(binding.amdsmi_init, ctypes.c_void_p).value
    if native_init != binding_init:
        raise RuntimeError("Torch and Python amdsmi load separate AMD SMI libraries")
    mappings = {
        tuple(line.split()[3:5])
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "/libamd_smi.so" in line
    }
    if len(mappings) != 1:
        raise RuntimeError(f"Expected one AMD SMI mapped file, found {len(mappings)}")
    report = {"single_amdsmi_library": True, "torch": torch.__version__}
    if args.gpu:
        from vllm.platforms import current_platform

        count = torch.cuda.device_count()
        if count != 2 or not current_platform.is_rocm():
            raise RuntimeError(f"Expected ROCm with two GPUs, got {count}, {current_platform}")
        devices = [torch.cuda.get_device_properties(i) for i in range(count)]
        if any("R9700" not in p.name or p.gcnArchName.split(":")[0] != "gfx1201"
               for p in devices):
            raise RuntimeError("Select exactly two R9700 / gfx1201 devices")
        report["devices"] = [p.name for p in devices]
        report["platform"] = type(current_platform).__name__
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
