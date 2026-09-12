#!/usr/bin/env python3
"""Patch the pinned GGUF loader to fit target expert loading in 64 GB host RAM.

Two workers otherwise overlap approximately 27.7 GiB temporary expert buffers.
Wrap only target loading and hot-expert compaction; see README.md beside this
file for measured motivation, collective boundaries, controls and review steps.
This project-specific patch is applied inside the image at build time.
"""
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import sys

EXPECTED_SHA256 = "804287bf87a034a0b7eb39c574bf17ef891786cf96b05221676538f7ae5921ff"
PLUGIN = Path("/opt/r9v/lib/python3.12/site-packages/vllm_gguf_plugin")
HERE = Path(__file__).resolve().parent


def transform(source):
    # The pinned block was audited to contain no inter-worker collectives.
    # Keep generic postprocessing outside: widening the lock needs a new audit.
    import_site = "from .gguf_files import GGUFModelFiles\n"
    start = "            model.load_weights(\n"
    end = "            process_weights_after_loading(model, model_config, target_device)\n"
    if source.count(import_site) != 1 or source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("Loader adaptation sites changed; review required")
    source = source.replace(import_site, import_site + "from .serialized_load import serialized_expert_load\n", 1)
    first, last = source.index(start), source.index(end)
    block = source[first:last]
    context = (
        "            # Experimental host-memory adaptation: keep initialization and\n"
        "            # generic post-load processing outside this TP-worker lock.\n"
        "            with serialized_expert_load(\n"
        "                target_with_manifest=(not is_draft_model and bool(\n"
        "                    os.environ.get(\"RADIANCE_TIERED_EXPERT_MANIFEST\")\n"
        "                )),\n"
        "                rank=torch.cuda.current_device(),\n"
        "                logger=logger,\n"
        "            ):\n"
    )
    return source[:first] + context + "".join("    " + line if line.strip() else line for line in block.splitlines(keepends=True)) + source[last:]


def main():
    # Review mode only reads an explicit local source and prints the diff.
    review = len(sys.argv) == 3 and sys.argv[1] == "--review"
    loader = Path(sys.argv[2]) if review else PLUGIN / "loader.py"
    original = loader.read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Base loader differs from pinned plugin 09b1199015c6b45de5c13dc4b36857ce27d9b0cd")
    patched = transform(original.decode())
    compile(patched, str(loader), "exec")
    if review:
        print("".join(difflib.unified_diff(original.decode().splitlines(keepends=True), patched.splitlines(keepends=True),
                                         fromfile="a/vllm_gguf_plugin/loader.py", tofile="b/vllm_gguf_plugin/loader.py")), end="")
        return
    loader.write_text(patched)
    shutil.copyfile(HERE / "serialized_load.py", PLUGIN / "serialized_load.py")
    manifest = Path("/opt/r9v-manifests/serialized-expert-load.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "status": "experimental-startup-memory-adaptation", "version": 1,
        "base_loader_sha256": EXPECTED_SHA256,
        "patched_loader_sha256": hashlib.sha256(patched.encode()).hexdigest(),
        "helper_sha256": hashlib.sha256((HERE / "serialized_load.py").read_bytes()).hexdigest(),
        "critical_section": "target model.load_weights plus materialize_hot_expert_cache",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
