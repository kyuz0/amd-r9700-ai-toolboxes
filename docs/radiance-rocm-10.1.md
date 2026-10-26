# Standalone Radiance on R9700

The `radiance-rocm-10.1` toolbox builds [Standalone Radiance](https://codeberg.org/StillDeadcode/radiance) from source for `gfx1201`, using ROCm 10.1 and its supplied compiler. It includes the native architecture/kernel plugins, media libraries, conversion tools and source/license receipts. It is a separate engine from the older vLLM Radiance toolbox.

The initial qualified source is v1.12.0, commit `5a9ce4912bb4ae5315e4a177f9e7d5b10d035766`. The build passed all 110 host tests. Qwen3.8-27B FP8 on two R9700s and MXFP4 on one R9700 passed sampled text, thinking, image input and tool calls. The FP8 target-only and DFlash2-7 profiles completed the nine-depth C1 HTTP workload through 64K history, with 2,048 new prompt tokens and 256 output tokens per measurement.

| Profile | History | Prefill tokens/s | Decode tokens/s |
| --- | ---: | ---: | ---: |
| Target only | 0 | 5,233.6 | 41.05 |
| Target only | 32,768 | 3,377.0 | 39.20 |
| Target only | 65,536 | 2,854.3 | 37.06 |
| DFlash2-7 | 0 | 1,702.3 | 96.08 |
| DFlash2-7 | 32,768 | 2,923.0 | 82.84 |
| DFlash2-7 | 65,536 | 279.2 | 124.29 |

These are two-repeat means on two R9700s in a four-card Threadripper 9970X / 64 GB host, using verified throughput-performance and automatic GPU fans. The workload is deterministic raw completion speed, separate from sampled chat or coding-agent scores.

## Install

```bash
podman pull docker.io/kyuz0/amd-r9700-toolboxes:radiance-rocm-10.1
toolbox create radiance-rocm-10.1 --image docker.io/kyuz0/amd-r9700-toolboxes:radiance-rocm-10.1
toolbox run --container radiance-rocm-10.1 radiance --help
```

The image also runs directly in Podman or Docker. Normal Toolbx entry was verified. No host ROCm SDK installation is required.

## Native model files

These containers include their tokenizer, vision and drafting tensors. A GGUF or vLLM checkpoint is a different format.

| Model | Repository revision | File | Bytes | GPU layout |
| --- | --- | --- | ---: | --- |
| Qwen3.8-27B FP8 | `StillDeadcode/qwen3.8-27b-fp8@edd43fda378af6b3b5e8981b6e936145be9608fd` | `qwen3.8-27b-fp8.rad` | 30,783,856,640 | TP2 |
| Qwen3.8-27B MXFP4 | `StillDeadcode/qwen3.8-27b-mxfp4@60bd4139f335205fbc120e5534329c30b691af0e` | `qwen3.8-27b-mxfp4.rad` | 19,377,119,232 | TP1 |

Use a pinned Hugging Face download or Cockpit's native model manager. The downloader's native transfer checks and exact file-size/revision coverage establish acquisition; inference qualification is separate.

## Launch Qwen27B FP8

Set `MODEL` to the complete native file. This profile binds only to local loopback and mounts the selected model read-only.

```bash
MODEL="$HOME/models/radiance/qwen38-27b-fp8-edd43fda/qwen3.8-27b-fp8.rad"
podman run --rm -it --name radiance-server \
  --device /dev/kfd --device /dev/dri --group-add keep-groups \
  --security-opt seccomp=unconfined --security-opt label=disable \
  -p 127.0.0.1:18890:18890 -v "$MODEL:/models/model.rad:ro" \
  docker.io/kyuz0/amd-r9700-toolboxes:radiance-rocm-10.1 \
  radiance --model /models/model.rad --host 0.0.0.0 --port 18890 \
  --tp 2 --tp-wire exact --placement all_vram --kv-cache-dtype fp8 \
  --max-model-len 8192 --max-num-seqs 1 --max-num-batched-tokens 2048 \
  --num-speculative-tokens 0 --reasoning-effort xhigh
```

For MXFP4, select its file and use `--tp 1`. The FP8 bundled DFlash2 profile uses `--num-speculative-tokens 7`. Vision remains enabled; `--mm-max-patches 0` disables image input. Context includes both prompt and generated tokens; additional sessions require additional cache capacity.

The API exposes `/health`, `/v1/models`, `/v1/chat/completions`, raw `/v1/completions`, `/tokenize` and `/metrics`. Qwen's sampled thinking profile uses temperature 1.0, top-p 0.95, top-k 20, min-p 0 and explicit thinking. The sampled non-thinking profile uses temperature 0.7, top-p 0.8, top-k 20, min-p 0 and presence penalty 1.5. Request settings override server defaults; select the thinking mode explicitly in clients.

## Build and publish

Run **Actions → Build & Publish Standalone Radiance** with the exact qualified source commit. The workflow builds the image, runs the host suite and no-device native smoke checks, uploads provenance, then publishes an immutable source/run tag and the rolling `radiance-rocm-10.1` channel. Compiler rebuilding is not part of this recipe; `RAD_HIP_VOPD_REPEATABLE=OFF` selects upstream's stock-toolchain build path.

The image records source revision, compiler version, build packages, licenses and the host-test completion marker under `/opt/radiance/share/doc/radiance/`. CI host tests do not replace model inference on the target GPUs.
