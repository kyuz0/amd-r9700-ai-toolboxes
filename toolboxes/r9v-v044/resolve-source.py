"""Record the selected release and resolve its supported AITER revision."""
import json
from pathlib import Path
import re
import subprocess
import sys

root, destination = map(Path, sys.argv[1:])
recipe = (root / "docker/Dockerfile.rocm10").read_text()
match = re.search(r"git -C /src/aiter checkout ([0-9a-f]{40})", recipe)
if not match:
    raise SystemExit("Upstream AITER selection changed; review its compatibility contract")
(destination / "aiter-ref.txt").write_text(match[1] + "\n")
records = {}
for name, path in {"r9v": root, "vllm": root / "vendor/vllm", "gguf_plugin": root / "vendor/vllm-gguf-plugin", "kernels": root / "kernels/r9v-gfx1201"}.items():
    records[name] = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
records["aiter"] = match[1]
(destination / "source-lock.json").write_text(json.dumps(records, indent=2) + "\n")
