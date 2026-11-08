#!/usr/bin/env python3
import sys
import os
import re
import struct
import argparse
import math
from typing import Dict, Any, List

# GGUF constants
GGUF_MAGIC = 0x46554747
GGUF_VALUE_TYPE = {
    0: "UINT8", 1: "INT8", 2: "UINT16", 3: "INT16", 4: "UINT32",
    5: "INT32", 6: "FLOAT32", 7: "BOOL", 8: "STRING", 9: "ARRAY",
    10: "UINT64", 11: "INT64", 12: "FLOAT64",
}
SCALAR_FORMAT = {
    0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
    6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d",
}
ARCH_METADATA_SUFFIXES = (
    ".block_count", ".context_length", ".attention.head_count_kv",
    ".attention.key_length", ".attention.value_length",
    ".attention.sliding_window_size",
)

class GGUFMetadataReader:
    """A minimal reader to get only the necessary KV metadata for cache calculation."""
    def __init__(self, path: str):
        self.path = path
        self.metadata: Dict[str, Any] = {}

    def read(self):
        with open(self.path, "rb") as f:
            self.f = f
            magic, _, _, metadata_kv_count = struct.unpack("<IIQQ", self.f.read(24))
            if magic != GGUF_MAGIC: raise ValueError("Invalid GGUF magic number")
            self._read_metadata(metadata_kv_count)
        return self

    def _read_string(self) -> str:
        (length,) = struct.unpack("<Q", self.f.read(8))
        return self.f.read(length).decode("utf-8", errors="replace")

    def _read_value(self, value_type_idx: int):
        value_type = GGUF_VALUE_TYPE.get(value_type_idx)
        if not value_type: raise ValueError(f"Unknown GGUF value type: {value_type_idx}")
        if value_type == "STRING": return self._read_string()
        scalar_format = SCALAR_FORMAT.get(value_type_idx)
        if scalar_format:
            return struct.unpack(scalar_format, self.f.read(struct.calcsize(scalar_format)))[0]
        self._skip_value(value_type_idx)

    def _skip_value(self, value_type_idx: int):
        value_type = GGUF_VALUE_TYPE.get(value_type_idx)
        if not value_type: raise ValueError(f"Unknown GGUF value type: {value_type_idx}")
        scalar_format = SCALAR_FORMAT.get(value_type_idx)
        if scalar_format:
            self.f.seek(struct.calcsize(scalar_format), 1)
        elif value_type == "STRING":
            (length,) = struct.unpack("<Q", self.f.read(8))
            self.f.seek(length, 1)
        elif value_type == "ARRAY":
            (array_type_idx, count) = struct.unpack("<IQ", self.f.read(12))
            scalar_format = SCALAR_FORMAT.get(array_type_idx)
            if scalar_format:
                self.f.seek(count * struct.calcsize(scalar_format), 1)
            else:
                for _ in range(count): self._skip_value(array_type_idx)

    def _read_metadata(self, count: int):
        for _ in range(count):
            key = self._read_string()
            (value_type_idx,) = struct.unpack("<I", self.f.read(4))
            # GGUF metadata is not required to put general.architecture first.
            if key in ("general.architecture", "general.name") or key.endswith(ARCH_METADATA_SUFFIXES):
                self.metadata[key] = self._read_value(value_type_idx)
            else:
                self._skip_value(value_type_idx)

def get_total_model_size_from_disk(gguf_file_path: str) -> int:
    """Calculates the total model size by finding all parts on disk."""
    match = re.search(r'-(\d{5})-of-(\d{5})\.gguf$', gguf_file_path, re.IGNORECASE)
    if not match:
        return os.path.getsize(gguf_file_path)

    base_path = gguf_file_path[:match.start()]
    total_parts_str = match.group(2)
    total_parts = int(total_parts_str)
    total_size, found_parts = 0, 0
    for i in range(1, total_parts + 1):
        part_file_name = f"{base_path}-{i:05d}-of-{total_parts_str}.gguf"
        if os.path.exists(part_file_name):
            total_size += os.path.getsize(part_file_name)
            found_parts += 1
    if found_parts != total_parts:
        print(f"WARNING: Expected {total_parts} parts, found {found_parts}. Size calculation may be incomplete.", file=sys.stderr)
    return total_size

def format_mem(size_bytes):
    mib = size_bytes / (1024 * 1024)
    if mib < 1024: return f"{mib:8.2f} MiB"
    return f"{mib / 1024:8.2f} GiB"

def run_estimator(gguf_file: str, context_sizes: List[int], overhead_gib: float):
    try:
        reader = GGUFMetadataReader(gguf_file).read()
        metadata = reader.metadata
        prefix = metadata.get("general.architecture")
        if not prefix: raise KeyError("Could not read 'general.architecture' from model metadata.")
        
        model_size_bytes = get_total_model_size_from_disk(gguf_file)
        overhead_bytes = int(overhead_gib * 1024**3)

        n_layers = metadata[f"{prefix}.block_count"]
        n_head_kv = metadata[f"{prefix}.attention.head_count_kv"]
        training_context = metadata.get(f"{prefix}.context_length", 0)
        n_embd_head_k = metadata[f"{prefix}.attention.key_length"]
        n_embd_head_v = metadata[f"{prefix}.attention.value_length"]
        swa_window_size = metadata.get(f"{prefix}.attention.sliding_window_size", 0)
        
        is_scout_model = "scout" in metadata.get("general.name", "").lower()
        if is_scout_model and swa_window_size == 0: n_layers_swa, n_layers_full, swa_window_size = 36, 12, 8192
        elif swa_window_size > 0: n_layers_swa, n_layers_full = n_layers, 0
        else: n_layers_swa, n_layers_full = 0, n_layers

        print(f"\n--- Model '{metadata.get('general.name', 'N/A')}' ---")
        if training_context > 0: print(f"Max Context: {training_context:,} tokens")
        print(f"Model Size: {format_mem(model_size_bytes).strip()} (from file size)")
        print(f"Incl. Overhead: {overhead_gib:.2f} GiB (for compute buffer, etc. adjustable via --overhead)")
        
        if training_context > 0:
            context_sizes = sorted(list(set([c for c in context_sizes if c <= training_context] + [c for c in [training_context] if c not in context_sizes])))
        else: context_sizes = sorted(context_sizes)
        
        bytes_per_token_per_layer = n_head_kv * (n_embd_head_k + n_embd_head_v) * 2
        
        print("\n--- Memory Footprint Estimation ---")
        print(f"{'Context Size':>15s} | {'Context Memory':>15s} | {'Est. Total VRAM':>15s}")
        print("-" * 51)
        for n_ctx in context_sizes:
            mem_full = n_ctx * n_layers_full * bytes_per_token_per_layer
            mem_swa = min(n_ctx, swa_window_size) * n_layers_swa * bytes_per_token_per_layer
            kv_cache_bytes = mem_full + mem_swa
            total_bytes = model_size_bytes + kv_cache_bytes + overhead_bytes
            print(f"{n_ctx:>15,} | {format_mem(kv_cache_bytes):>15s} | {format_mem(total_bytes):>15s}")
            
    except (FileNotFoundError, ValueError, struct.error, NotImplementedError, KeyError) as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Calculate VRAM requirements for a GGUF model, including a configurable overhead for compute buffers.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("gguf_file", help="Path to the GGUF model file (any part of a multi-part model).")
    parser.add_argument("-c", "--contexts", nargs='+', type=int, default=[4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576], help="Space-separated list of context sizes to calculate.")
    parser.add_argument("--overhead", type=float, default=2.0, help="Estimated overhead in GiB for compute buffers, drivers, etc. (default: 2.0)")
    args = parser.parse_args()
    run_estimator(args.gguf_file, args.contexts, args.overhead)

if __name__ == "__main__":
    main()
