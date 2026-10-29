# Standalone Radiance on R9700

The `radiance-rocm-10.1` toolbox builds [Standalone Radiance](https://codeberg.org/StillDeadcode/radiance) from source for `gfx1201`, using ROCm 10.1 and its supplied compiler. It includes the native architecture/kernel plugins, media libraries, conversion tools and source/license receipts. It is a separate engine from the older vLLM Radiance toolbox.

The qualified source is v1.12.0, commit `5a9ce4912bb4ae5315e4a177f9e7d5b10d035766`. The source build passed all 110 host tests. Qwen3.8-27B FP8 on two R9700s, MXFP4 on one R9700 and Flash Next FP8/IQ4R on four R9700s passed sampled text, thinking, image input and tool calls. Target-only and bundled drafting profiles completed the nine-depth C1 HTTP workload through 64K history, with 2,048 new prompt tokens and 256 output tokens per measurement.

| Artifact | Mode | GPUs | PP at 0 | TG at 0 | PP at 64K | TG at 64K |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3.8-27B FP8 | Target only | 2 | 5,233.6 | 41.05 | 2,854.3 | 37.06 |
| Qwen3.8-27B FP8 | DFlash2-7 | 2 | 1,702.3 | 96.08 | 279.2 | 124.29 |
| Qwen3.8-27B MXFP4 | Target only | 1 | 1,908.4 | 38.50 | 667.4 | 31.82 |
| Qwen3.8-27B MXFP4 | DFlash2-7 | 1 | 1,229.5 | 114.24 | 141.2 | 73.59 |
| Flash Next FP8/IQ4R | Target only / RAM | 4 | 6,443.5 | 121.44 | 5,070.2 | 117.10 |
| Flash Next FP8/IQ4R | MTP3 / RAM | 4 | 7,241.9 | 319.25 | 4,519.9 | 323.58 |

These are two-repeat mean rates in tokens/s on a four-card Threadripper 9970X / 64 GB host, using verified throughput-performance and automatic GPU fans under an explicit user-approved benchmark-policy exception. Each row uses only the listed GPUs. PP measures useful follow-up tokens through the first response token, including any reported history replay. The workload is deterministic raw completion speed, separate from sampled chat or coding-agent scores.

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
| Qwen3.8-27B FP8 | `StillDeadcode/qwen3.8-27b-fp8@edd43fda378af6b3b5e8981b6e936145be9608fd` | `qwen3.8-27b-fp8.rad` | 30,783,856,640 | TP2 or TP4 |
| Qwen3.8-27B MXFP4 | `StillDeadcode/qwen3.8-27b-mxfp4@60bd4139f335205fbc120e5534329c30b691af0e` | `qwen3.8-27b-mxfp4.rad` | 19,377,119,232 | TP1 or TP4 |
| Qwen3.8-Flash-Next FP8/IQ4R | `StillDeadcode/qwen3.8-next-flash-fp8-iq4r-moe@8267a67384583f6be309981baf878b09ff900a9a` | `qwen3.8-next-flash-fp8-iq4r-moe.rad` | 121,969,901,568 | TP4 |

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

## Four-GPU Qwen27 FP8

The native FP8 artifact also completed matched target-only and DFlash2-7 depth curves on four R9700s with the same published Radiance 1.12.0 image. To reproduce the measured allocation, use the FP8 command above with `--tp 4 --max-model-len 67840 --max-num-seqs 16` and add `--checkpoint-slots 144`. Keep `--num-speculative-tokens 0` for target-only decoding or select `7` for DFlash2. FP8 KV, exact inter-GPU communication and GPU weight placement remain as shown above.

The 144 hybrid-state checkpoints reserve about 20.65 GiB of host RAM in addition to other process memory. The model weights remain in VRAM. The server allocates 16 sequences; the client separately selects how many requests run simultaneously. Every row below uses all four GPUs, including the one-request rows.

| Requests | Mode | Aggregate PP / TG at 8K (tokens/s) | Aggregate PP / TG at 64K (tokens/s) |
| ---: | --- | ---: | ---: |
| 1 | Target only | 6,826.65 / 69.37 | 4,791.81 / 63.78 |
| 1 | DFlash2-7 | 6,593.97 / 243.64 | 4,708.50 / 133.89 |
| 4 | Target only | 6,308.07 / 219.81 | 3,672.79 / 170.67 |
| 4 | DFlash2-7 | 6,326.95 / 494.47 | 3,689.00 / 269.16 |
| 8 | Target only | 6,259.07 / 322.27 | 3,725.17 / 218.62 |
| 8 | DFlash2-7 | 6,340.79 / 551.27 | 3,735.80 / 304.06 |
| 16 | Target only | 6,182.95 / 419.47 | 455.62 / 52.70 |
| 16 | DFlash2-7 | 6,300.50 / 578.32 | 500.77 / 61.27 |

Both modes completed all nine history depths with two repeats, totaling 1,044 measured requests with matching logical prime/follow-up inputs. At 64K, one, four and eight requests retained the complete history; sixteen requests retained a mean 49,280 tokens and replayed 16,256 in both modes. These rates include that replay. See the [complete paired speed curves](https://local-llm-benchmarks.dev/speed) by selecting R9700, four GPUs, Qwen3.8-27B, FP8 and Standalone Radiance, then the request count and decoding mode.

## Four-GPU Qwen27 MXFP4

The native MXFP4 artifact completed the same four-card target-only and DFlash2-7 workload. Select `qwen3.8-27b-mxfp4.rad` and use `--tp 4 --max-model-len 67840 --max-num-seqs 16 --checkpoint-slots 144`, with `--num-speculative-tokens 0` or `7`. This uses the [same FP8-KV and host-checkpoint allocation](#four-gpu-qwen27-fp8) described above, including about 20.65 GiB of host state. All rows use four GPUs; request count is client concurrency.

| Requests | Mode | Aggregate PP / TG at 8K (tokens/s) | Aggregate PP / TG at 64K (tokens/s) |
| ---: | --- | ---: | ---: |
| 1 | Target only | 6,951.52 / 100.62 | 4,845.35 / 88.95 |
| 1 | DFlash2-7 | 6,866.16 / 341.85 | 4,753.74 / 255.33 |
| 4 | Target only | 6,583.42 / 296.00 | 3,732.60 / 210.89 |
| 4 | DFlash2-7 | 6,475.65 / 589.78 | 3,721.66 / 342.43 |
| 8 | Target only | 6,456.68 / 399.35 | 3,789.61 / 249.09 |
| 8 | DFlash2-7 | 6,477.50 / 591.26 | 3,794.28 / 324.65 |
| 16 | Target only | 6,466.94 / 485.15 | 461.67 / 54.06 |
| 16 | DFlash2-7 | 6,441.93 / 575.80 | 513.90 / 63.59 |

Both modes completed all nine depths and two repeats: 1,044 measured requests with matching logical prime/follow-up inputs. At 64K, one, four and eight requests retained all history; sixteen retained a mean 49,280 tokens and replayed 16,256 in both modes. The rates include this replay. In the [speed viewer](https://local-llm-benchmarks.dev/speed), select R9700, four GPUs, Qwen3.8-27B, MXFP4 and Standalone Radiance to compare both full curves at the desired request count.

## Launch Flash Next

Select its native file, use `--tp 4` and add `--ngram-placement ram` to the launch command above. Target-only decoding uses `--num-speculative-tokens 0`; the bundled MTP profile uses `--num-speculative-tokens 3`.

The 47.68 GiB n-gram table lives in pinned host RAM. Allow about 54 GiB of available host memory at startup, including loading headroom. Main weights and experts use the four GPU pools; a small token-embedding pool also uses pinned host memory. `--placement all_vram` does not place the n-gram table in VRAM. Start with an 8,192-token context and one session. Complete C4/C8/C16 standard-depth curves used 16 server sequences. At 64K, MTP3 aggregate decode reached 477.78/186.26/41.61 tokens/s respectively, with increasing history replay at C8/C16. Prefer one or four active clients for deep-context work.

## Build and publish

Run **Actions → Build & Publish Standalone Radiance**. The default resolves the latest stable release and records its exact commit. Enter an explicit full commit to reproduce the measured build. The workflow builds the image, runs the host suite and no-device native smoke checks, uploads provenance, then publishes an immutable source/run tag and the rolling `radiance-rocm-10.1` channel. Compiler rebuilding is not part of this recipe; `RAD_HIP_VOPD_REPEATABLE=OFF` selects upstream's stock-toolchain build path.

The image records source revision, compiler version, build packages, licenses and the host-test completion marker under `/opt/radiance/share/doc/radiance/`. CI host tests do not replace model inference on the target GPUs.

## Frozen-continuation quality

The frozen-continuation panels completed on the published image with target-only scoring. NLL is per local target token; lower is better. These are hosted-continuation checks, without an original-weight full-logit parity claim.

| Native artifact | Short100 NLL | Long12 NLL | Local target tokens, short / long |
| --- | ---: | ---: | ---: |
| Qwen3.8-27B FP8 | 0.281940 | 0.099176 | 5,836 / 764 |
| Qwen3.8-27B MXFP4 | 0.318670 | 0.147677 | 5,836 / 764 |
| Flash Next FP8/IQ4R | 0.288974 | 0.130511 | 5,696 / 766 |
