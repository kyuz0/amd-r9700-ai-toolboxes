#!/usr/bin/env python3
"""Extract the pinned launcher environment/argv into an in-container command.

Preserves upstream model settings; replaces container orchestration with exec
and adds the measured synchronous scheduling flag. Source drift fails the build.
"""
import hashlib
from pathlib import Path
import sys

LAUNCH_SHA = "fe56d757a5ed71ae72176d25fcb31a67b432e4eaf45b5a19ac941fb58da84e4e"
PROFILE_SHA = "4bd3dffc36332a7752b02cb53fb5c5d78db1623ce93e43bf0d100611563a7b05"


def render(root):
    launch = (root / "scripts/launch.sh").read_bytes()
    profile = root / "profiles/qwen38-flash-next/dual-r9700/profile.env"
    if hashlib.sha256(launch).hexdigest() != LAUNCH_SHA:
        raise ValueError("Pinned upstream launcher changed")
    if hashlib.sha256(profile.read_bytes()).hexdigest() != PROFILE_SHA:
        raise ValueError("Pinned upstream profile changed")
    source = launch.decode()
    setup = source[source.index("custom_scopes=${R9V_CUSTOM_SCOPES_FOR_PROFILING:-$profiler_scopes}\n"):source.index("if [[ $R9V_PREFLIGHT == 1 ]]; then\n")]
    container = source[source.index("docker run --detach ") :]
    environment = []
    for line in container.splitlines():
        if line.startswith("    --env "):
            environment.append("export " + line.removeprefix("    --env ").removesuffix(" \\") + "\n")
    if len(environment) != 75:
        raise ValueError(f"Unexpected upstream environment size: {len(environment)}")
    argv = container.split('    "$image" \\\n', 1)[1].split("\nprintf 'Started", 1)[0].rstrip()
    return '''#!/usr/bin/env bash
set -euo pipefail
: "${R9V_PLE_WORKER_TIMING:=1}"
set -a
source /opt/r9v-src/profiles/qwen38-flash-next/dual-r9700/profile.env
set +a
# The tested 64 GB profile uses SSD PLE and two GPUs.
[[ $R9V_PLE_RESIDENCY_MODE == ssd && $R9V_TENSOR_PARALLEL_SIZE == 2 ]] || {
    echo 'This toolbox profile requires SSD PLE and tensor parallel size 2.' >&2; exit 2;
}
model_dir=/models
ple_path=/ple/per_layer_token_embd.iq4_nl.bin
visible_devices=$R9V_VISIBLE_DEVICES
hip_visible_devices=0,1
container=r9v-latest-qualification
repo_root=/opt/r9v-src
runtime_cache_root=/cache/vllm
: "${R9V_PLE_HOST_FENCE:=1}"
ple_mmap_host_register=0
profiler_scopes=0
profiler_args=()
export HOME=/cache/home XDG_CACHE_HOME=/cache/xdg
export TRITON_CACHE_DIR=/cache/triton TORCHINDUCTOR_CACHE_DIR=/cache/torch
mkdir -p "$HOME" "$XDG_CACHE_HOME" "$TRITON_CACHE_DIR" "$TORCHINDUCTOR_CACHE_DIR"
''' + setup + "\n" + "".join(environment) + "\nexec vllm serve \\\n" + argv + ' \\\n    --no-async-scheduling "$@"\n'


if __name__ == "__main__":
    Path(sys.argv[2]).write_text(render(Path(sys.argv[1])))
