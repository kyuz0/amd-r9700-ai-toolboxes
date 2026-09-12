# Qwen3.8 Flash Next — R9V / ROCm 10

Tested with **2× Radeon AI PRO R9700 32 GB, 64 GB host RAM and NVMe**.
On a three-R9700 host, this profile uses two selected GPUs; three-way tensor
parallelism is not supported by this packaged profile. Use rootless Podman/crun
with access to `/dev/kfd` and `/dev/dri`. Allow about **118 GiB for model + PLE**,
plus **21 GB for the image** and room for compilation caches.

## Publish the image manually

GitHub → **Actions → Build & Publish R9V (manual) → Run workflow**, or:

```bash
gh workflow run build-r9v.yml --ref main
```

Uses the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
Builds from source, runs CPU dependency/SHM/AMD SMI identity checks, then pushes:

- `docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0`
- A versioned tag containing the timestamp, commit, run ID and attempt.

No schedule, push trigger or llama.cpp poller triggers this workflow. The tag
becomes available after the first successful manual run. CI has no GPU tests.

## Download and prepare the model

From this repository's root:

```bash
export R9V_IMAGE=docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0
podman pull "$R9V_IMAGE"
mkdir -p "$HOME/models/R9V-Qwen3.8-IQ4_XS" "$HOME/r9v-data"

# Read the model's Qwen Community License 1.0 before accepting.
podman run --rm --user 0:0 --security-opt label=disable \
  -v "$HOME/models/R9V-Qwen3.8-IQ4_XS:/models" \
  "$R9V_IMAGE" r9v-model download --accept-model-license

podman run --rm --user 0:0 --security-opt label=disable \
  -v "$HOME/models/R9V-Qwen3.8-IQ4_XS:/models:ro" \
  -v "$HOME/r9v-data:/ple" \
  "$R9V_IMAGE" r9v-model prepare
```

Downloads the pinned [R9V IQ4_XS package](https://huggingface.co/Dyluhn/Qwen3.8-Flash-Next-R9V-IQ4_XS/tree/bf836f0c20b6c92fcad4226ad3115eb8a19f7582),
including FP8 MTP and the Q8 vision projector. Preparation extracts and hashes
`$HOME/r9v-data/per_layer_token_embd.iq4_nl.bin` (26.82 GiB).
To reuse existing files, skip download/preparation and verify the package:

```bash
podman run --rm --user 0:0 --security-opt label=disable \
  -v "$HOME/models/R9V-Qwen3.8-IQ4_XS:/models:ro" \
  "$R9V_IMAGE" r9v-model verify
```

## Run with Podman

```bash
cp toolboxes/r9v/config.env.example "$HOME/r9v-data/toolbox.env"
# Edit paths and R9V_VISIBLE_DEVICES if your GPU pair is not 0,1.
export R9V_CONFIG_FILE="$HOME/r9v-data/toolbox.env"
bash toolboxes/r9v/run.sh
podman logs -f r9700-r9v
```

Startup takes several minutes. The helper mounts model/PLE read-only, keeps
caches under `$HOME/r9v-data/cache-toolbox-rocm10`, and binds only to loopback.
Once ready:

```bash
curl --fail http://127.0.0.1:8004/health
curl --fail http://127.0.0.1:8004/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-flash-next","messages":[{"role":"user","content":"Explain an LRU cache."}],"temperature":0,"max_tokens":256,"chat_template_kwargs":{"enable_thinking":false}}'
```

Client URL: **`http://127.0.0.1:8004/v1`**; model: **`qwen3.8-flash-next`**.
For remote access: `ssh -L 8004:127.0.0.1:8004 USER@GPU_HOST`.

```bash
podman stop --time 30 r9700-r9v
podman start r9700-r9v               # resume the same configuration
```

To apply edited configuration:

```bash
podman stop --time 30 r9700-r9v
podman rm r9700-r9v
bash toolboxes/r9v/run.sh
```

## Toolbox shell

```bash
toolbox create --image docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0 r9700-r9v-shell
toolbox enter r9700-r9v-shell
# Or enter the running server:
podman exec -it r9700-r9v bash
```

Use the Podman helper above to launch inference with the required mounts.
The image also provides `r9v-serve`, `r9v-model` and `vllm` directly.

## Build locally

```bash
podman build --layers --jobs=1 --build-arg MAX_JOBS=4 \
  -f toolboxes/Dockerfile.r9v-rocm-10.0 \
  -t docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0 toolboxes
# Docker equivalent:
docker build --build-arg MAX_JOBS=4 \
  -f toolboxes/Dockerfile.r9v-rocm-10.0 \
  -t kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0 toolboxes
```

The context is `toolboxes/`. No model weights or local research files are needed.
Source build tested with Podman; allow substantial temporary disk space. CI uses
one compiler job to fit hosted-runner RAM. [Source/model pins](../toolboxes/r9v/source-lock.json)
and package records are included in the image under `/opt/r9v-manifests`.

## Configuration and results

The helper preserves the [exact launch arguments/environment](../toolboxes/r9v/measured-launch.json).
Main settings:

| Setting | Value |
|---|---|
| Target / draft | IQ4_XS / FP8 MTP, depth 2 |
| Tensor parallel / sequences | 2 GPUs / 1 sequence |
| Context / batched prefill | 131,072 / 1,024 tokens |
| KV memory | 2,285,670,400 bytes per GPU |
| CPU expert offload | 112.5 logical GB; per-device `112.5,112.5` |
| Expert cache / PLE | Rank-1 LRU 16 slots / NVMe mmap |
| Scheduling | Synchronous (`--no-async-scheduling`) |
| Graph sizes / tools | `[1,3]` / `qwen3_coder`, automatic tool choice |

The offload number is logical weight accounting, not physical RAM allocation.
Required fixes included [serialized expert loading](../toolboxes/r9v/serialized-load/README.md)
to fit 64 GB RAM, library
paths for Torch's SHM executable, and removal of Ubuntu's default UID-1000 user
so Toolbx can create the host user. ROCm 10, Torch, Triton and native kernels
are built as one pinned stack.

The image also links AMD SMI's development-library aliases to its runtime copy.
The first Docker Hub build contained two independent copies, causing
`Failed to infer device type` after Torch imported. CI now checks that Torch and
Python AMD SMI load the same library. Rebuild the manual workflow and pull the
updated image if you have that first build; model files do not need changing.

Measured after sustained use, with 256 output tokens, thinking off and one request
at a time:

| Workload | Decode | First text |
|---|---:|---:|
| Prose | 76.7 tok/s | 0.171 s |
| Code | 85.5 tok/s | 0.183 s |
| Reasoning prompt | 72.7 tok/s | 0.338 s |
| Near-8K input | 78.7 tok/s | 3.473 s |

**8K prefill: 2,359 input tok/s** (input tokens ÷ time to first text).
The initial panel was slower at 43–49 decode tok/s; the reason for the increase
is unresolved. An earlier 129,935-token request took 67.4 s to first text.
A **30m44s mixed test passed 210 benchmark requests and 126 functional checks**,
with no OOM events and at least 25.03 GiB available RAM. Vision recognized the
test shapes but added Markdown fences, failing strict JSON parsing.
