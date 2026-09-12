#!/usr/bin/env python3
"""Run the generated shell against fake files/vLLM and measured container argv.

Usage: python3 toolboxes/r9v/test-launch.py /path/to/pinned/R9V
No containers, GPU requests or real model files are used.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("make_serve", here / "make-serve.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
source = Path(sys.argv[1]).resolve()
expected = json.loads((here / "measured-launch.json").read_text())

with tempfile.TemporaryDirectory(prefix="r9v-launch-test-") as directory:
    root = Path(directory)
    script = generator.render(source)
    substitutions = {"/opt/r9v-src": str(source), "/models": str(root / "models"),
                     "/ple": str(root / "ple"), "/cache": str(root / "cache")}
    for old, new in substitutions.items():
        script = script.replace(old, new)
    launch = root / "serve.sh"
    launch.write_text(script)
    subprocess.run(["bash", "-n", str(launch)], check=True)
    files = [f"target/Qwen3.8-Flash-Next-UD-IQ4_XS-0000{n}-of-00003.gguf" for n in (1, 2, 3)]
    files += ["metadata/config.json", "mtp/config.json", "mtp/model.safetensors",
              "vision/mmproj-Qwen3.8-Flash-Next-Q8_0.gguf",
              "manifests/hot-manifest-q4-vision-128k-multiprompt-r1-lru16-neutral.json"]
    for name in files:
        path = root / "models" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    ple = root / "ple/per_layer_token_embd.iq4_nl.bin"
    ple.parent.mkdir()
    ple.touch()
    binary = root / "vllm"
    binary.write_text("#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({'argv':sys.argv[1:], 'environment':dict(os.environ)}))\n")
    binary.chmod(0o755)
    env = {"PATH": f"{root}:{os.environ['PATH']}", "HOME": str(root)}
    result = subprocess.run(["bash", str(launch)], env=env, text=True, capture_output=True, check=True)
    actual = result.stdout
    for old, new in substitutions.items():
        actual = actual.replace(new, old)
    actual = json.loads(actual)
    assert actual["argv"] == expected["argv"], (actual["argv"], expected["argv"])
    for key, value in expected["environment"].items():
        assert actual["environment"].get(key) == value, (key, actual["environment"].get(key), value)
    print(f"PASS: exact model argv and {len(expected['environment'])} environment values match recorded settings")
    result = subprocess.run(["bash", str(launch)], env={**env, "R9V_PLE_RESIDENCY_MODE": "pinned"}, capture_output=True)
    assert result.returncode == 2, "64 GB profile accepted pinned PLE mode"
    ple.unlink()
    result = subprocess.run(["bash", str(launch)], env=env, capture_output=True)
    assert result.returncode == 1 and b"Required file missing" in result.stderr
    print("PASS: unsupported PLE mode and missing model payload fail before vLLM")
