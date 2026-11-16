# Standalone Radiance on four R9700s

The `radiance-rocm-10.1` toolbox builds [Radiance](https://codeberg.org/StillDeadcode/radiance) for `gfx1201` with the supplied ROCm 10.1 compiler. The qualified configuration uses **four Radeon AI PRO R9700s and Qwen3.8-Flash-Next IQR-V4**, with native MTP speculative decoding. The tested host has a Threadripper 9970X and 64 GB system RAM.

Radiance v2.1.0, commit `2a2b756371c26f2768b8d129a098df275ace2c73`, passed 180 host tests and four-device inference checks. This release uses native YAML configuration; `rad-yaml` converts the command options below into that configuration.

## Install and choose a profile

In [AI Toolbox Cockpit](https://github.com/kyuz0/ai-toolbox-cockpit), select the R9700 platform and Standalone Radiance. Install or update the existing `radiance-rocm-10.1` toolbox, download Qwen3.8-Flash-Next IQR-V4, then choose its serving profile. MTP defaults to three draft tokens.

| Profile | Context default | Configured server slots | Memory placement |
| --- | ---: | ---: | --- |
| Native context, disk | 262,144 | 16 | Disk n-grams, 144 recurrent snapshots |
| Native context, RAM | 262,144 | 16 | RAM n-grams, 48 tip-only recurrent snapshots, GPU embeddings |
| Single-user 1M extension | 1,000,000 | 1 | Disk n-grams, 144 recurrent snapshots, YaRN `4:262144` |

The native disk profile completed the full nine-depth speed workload through 64K history at 1, 4, 8, 10 and 16 simultaneous requests. At full 262K context, four simultaneous sessions retained their complete histories in both repeats. At 8, 10 and 16 sessions, all requests completed, but only five histories per batch remained cached; the others were recomputed. Choose up to four active sessions for the tested fully retained 262K workload. Five through seven active sessions have not been tested.

The single-user extension processed 999,744 input tokens and generated 256 output tokens using the model owner's [documented YaRN extension](https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/812d96e10a0dd82b69d749e68693698cf6c36daa/README.md). This establishes input capacity, not answer quality over a million tokens or concurrent 1M-session support.

## Model artifact

Download the native RAD file through Cockpit's Model Manager. A GGUF or vLLM checkpoint is not interchangeable with this format.

| Item | Value |
| --- | --- |
| Repository | [StillDeadcode/qwen3.8-next-flash-iqr-v4](https://huggingface.co/StillDeadcode/qwen3.8-next-flash-iqr-v4) |
| Qualified revision | `679c943216e5a33da5f458b5da378586219e874b` |
| File | `qwen3.8-next-flash-iqr-v4.rad` |
| Size | 121,678,372,864 bytes |
| GPU allocation | TP4, exact inter-GPU transport, i8 KV |

The artifact includes its tokenizer and native draft tensors. Expert weights remain in VRAM. The disk profile reads n-grams from the model file and reserves about 15.93 GiB of host memory for recurrent snapshots; it left approximately 37 GiB of host memory available during the measured workload.

The RAM profile keeps approximately 47.7 GiB of n-grams and 5.31 GiB of recurrent snapshots in host memory, with embeddings in VRAM. It is faster on the measured 0–64K workload, but left only about 1 GiB of host memory available. Prefer disk n-grams when other applications need RAM. Both profiles retained four active full-window sessions; at eight, RAM retained four histories per batch and reached a 139-second maximum first-token wait, versus five histories and 106 seconds for disk. The speed advantage at shorter histories does not establish better full-window concurrency.

## Manual launch

Set `MODEL` to the complete native file. This command uses the measured native-context allocation and exposes the API only on local loopback.

```bash
MODEL="$HOME/models/radiance/qwen38-flash-iqrv4-679c9432/qwen3.8-next-flash-iqr-v4.rad"
podman run --rm -it --name radiance-server \
  --device /dev/kfd --device /dev/dri --group-add keep-groups \
  --security-opt seccomp=unconfined --security-opt label=disable \
  -p 127.0.0.1:18890:18890 -v "$MODEL:/models/model.rad:ro" \
  docker.io/kyuz0/amd-r9700-toolboxes:radiance-rocm-10.1 \
  bash -ceu 'rad-yaml "$@" > /tmp/radiance.yaml; radiance --config /tmp/radiance.yaml --check; exec radiance --config /tmp/radiance.yaml' radiance-launch \
  --model /models/model.rad --host 0.0.0.0 --port 18890 \
  --tp 4 --tp-wire exact --placement all_vram --kv-cache-dtype i8 \
  --max-model-len 262144 --max-num-seqs 16 --max-num-batched-tokens 2048 \
  --ngram-placement disk --checkpoint-slots 144 --prefill-interleave 0 \
  --num-speculative-tokens 3 --reasoning-effort xhigh
```

For the RAM profile, replace `--ngram-placement disk --checkpoint-slots 144` with `--ngram-placement ram --checkpoint-slots 48 --checkpoint-policy tip-only --embedding-placement vram --host-headroom-mib 2048`. Keep the other native-profile settings, including 16 configured slots and interleave0.

For the tested single-user extension, replace `--max-model-len 262144 --max-num-seqs 16` with `--max-model-len 1000000 --max-num-seqs 1 --rope-scaling yarn:4:262144`. For decoding without MTP, set `--num-speculative-tokens 0`.

Keep the native recipe's 16 configured slots when reproducing its allocation; active request count is controlled separately by clients. Reducing configured slots can change the attention-cache pool. The 1M profile was explicitly tested with one slot.

The text measurements kept the artifact's vision tower loaded at its automatic allocation. The command above preserves that allocation. API endpoints include `/health`, `/v1/models`, `/v1/chat/completions`, `/v1/completions`, `/tokenize` and `/metrics`.

## Measured speed

Fixed MTP3, interleave0, four GPUs and 16 configured slots; aggregate prompt processing / generation in tokens/s. Each placement uses its profile above:

| Simultaneous requests | Disk, fresh prompt | Disk, 64K history | RAM, 64K history |
| ---: | ---: | ---: | ---: |
| 1 | 8,810 / 325 | 6,546 / 273 | 7,238 / 332 |
| 4 | 8,198 / 555 | 6,756 / 459 | 7,043 / 523 |
| 8 | 8,122 / 645 | 6,834 / 523 | 7,052 / 546 |
| 10 | 8,318 / 616 | 7,020 / 543 | 7,092 / 561 |
| 16 | 8,114 / 592 | 6,905 / 574 | 7,101 / 588 |

All nine depths, two repeats and exact 256-token outputs completed without history replay. Each measurement appends 2,048 tokens to a primed history. These are deterministic raw-completion speed measurements; they do not establish coding-agent quality. Aggregate generation is measured over the batch output span and is not an individual user's rate. The host used throughput-performance and automatic GPU fans.

## Build and publish

Run **Actions → Build & Publish Standalone Radiance**. The default resolves the latest stable release and records its exact commit. Use `2a2b756371c26f2768b8d129a098df275ace2c73` to reproduce the qualified source. The workflow builds the image, runs host tests and native no-device smoke checks, uploads provenance, and publishes an immutable source/run tag plus the existing rolling `radiance-rocm-10.1` channel.

`RAD_HIP_VOPD_REPEATABLE=OFF` selects the stock-toolchain build path; no LLVM rebuild is required. Source revision, compiler version, package/license receipts and the host-test completion marker are stored under `/opt/radiance/share/doc/radiance/`. GPU inference checks remain separate from CI host tests.
