# AMD R9700 Llama.cpp Toolboxes

Pre-built `llama.cpp` containers for running LLMs with Vulkan or ROCm acceleration on **AMD Radeon AI PRO R9700** GPUs (`gfx1201`).

## Recommended setup: AI Toolbox Cockpit

[AI Toolbox Cockpit](https://github.com/kyuz0/ai-toolbox-cockpit) is the preferred way to install, launch, and update these toolboxes. It provides tested, pre-configured profiles; supports Toolbx and Distrobox; and can run supported servers directly with Podman or Docker, so Toolbx is not required.

```bash
pipx install git+https://github.com/kyuz0/ai-toolbox-cockpit.git
ai-toolbox-cockpit
```

The repository's [`refresh-toolboxes.sh`](refresh-toolboxes.sh) remains available for manual Toolbx refreshes. The Cockpit is recommended for normal installation and updates.

## Available toolboxes

Images are hosted on [Docker Hub](https://hub.docker.com/r/kyuz0/amd-r9700-toolboxes/tags). The standard images are automatically rebuilt on `llama.cpp` updates, while the ROCmFPX image is rebuilt when its fork updates.

| Tag | Backend | Notes |
| :--- | :--- | :--- |
| `vulkan-radv` | Vulkan (Mesa RADV) | Most stable and compatible. Recommended for most users and models. |
| `vulkan-rocmfpx` | Vulkan (ROCmFPX, Fedora 43) | Vulkan-only `charlie12345/ROCmFPX` build with ROCmFP3/FP4/FP6/FP8 weight formats. No ROCm runtime dependency. |
| `rocm-10.0` | ROCm 10.0 Core SDK (Fedora 44) | Stable ROCm Core SDK build using AMD's supported `gfx1201` package set. |
| `therock-nightly` | TheRock Nightly (Fedora 43) | Tracks AMD's latest multi-architecture `gfx120X-all` nightly for RDNA 4 (`gfx1200`/`gfx1201`). |

## Watch the YouTube Video

[![Watch the YouTube Video](https://img.youtube.com/vi/dgyqBUD71lg/maxresdefault.jpg)](https://youtu.be/dgyqBUD71lg) 

## Manual setup and usage

Use this section only if you prefer to create and maintain the container yourself. For the guided, tested path across Toolbx, Distrobox, Podman, and Docker, use [AI Toolbox Cockpit](#recommended-setup-ai-toolbox-cockpit).

### 1. Create a Toolbox
**Which backend to choose?**
*   **Vulkan (RADV)**: Recommended for **stability**. It works reliably with almost all models.
*   **ROCm**: Recommended for **maximum performance**.
    *   **ROCm 10.0** is the stable release. **TheRock nightly** tracks AMD's latest multi-arch nightly build. Performance can vary depending on the model architecture, so check the [Benchmarks](https://kyuz0.github.io/amd-r9700-ai-toolboxes/).
*   **Vulkan (ROCmFPX)**: Custom ROCmFPX fork for ROCmFP3/FP4/FP6/FP8 model formats.

**Option A: Vulkan (RADV) [Recommended]**
```bash
toolbox create r9700-llama-vulkan-radv \
  --image docker.io/kyuz0/amd-r9700-toolboxes:vulkan-radv \
  -- --device /dev/dri --group-add video --security-opt seccomp=unconfined
```

**Option B: ROCm 10.0**
```bash
toolbox create r9700-llama-rocm-10.0 \
  --image docker.io/kyuz0/amd-r9700-toolboxes:rocm-10.0 \
  -- --device /dev/dri --device /dev/kfd \
  --group-add video --group-add render --group-add sudo --security-opt seccomp=unconfined
```

**Option C: Vulkan (ROCmFPX)**
```bash
toolbox create r9700-llama-vulkan-rocmfpx \
  --image docker.io/kyuz0/amd-r9700-toolboxes:vulkan-rocmfpx \
  -- --device /dev/dri --group-add video --security-opt seccomp=unconfined
```

> **Ubuntu Users**: `toolbox` may have issues with GPU access. Use [Distrobox](https://github.com/89luca89/distrobox) instead. See [Detailed Guide](#ubuntu-users-distrobox) below.

### 2. Enter the Toolbox
```bash
toolbox enter r9700-llama-vulkan-radv
# or: toolbox enter r9700-llama-rocm-10.0
# or: toolbox enter r9700-llama-vulkan-rocmfpx
```

### 3. Download a Model

**Option A: Manual Download (Recommended)**
Use the `hf` tool to download the model GGUF files to a local directory.

```bash
# Download to models/qwen3-coder-30B-A3B/
HF_HUB_ENABLE_HF_TRANSFER=1 hf download unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF \
  BF16/Qwen3-Coder-30B-A3B-Instruct-BF16-00001-of-00002.gguf \
  --local-dir .
```

**Multi-shard Models:**
If a model is split into multiple files (e.g., `00001-of-00005.gguf`), you must download **all** shards to the same folder. The command above ensures all parts are downloaded.

> [!NOTE]
> The old `huggingface-cli` is deprecated. Use the modern `hf` tool (part of `huggingface_hub`).

**Option B: Automatic Download (via llama.cpp)**
`llama.cpp` can automatically download models from the Hugging Face Hub to its internal cache (`~/.cache/huggingface/hub`).

```bash
# Automatically download and run
llama-cli -hf unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF -hf-file BF16/Qwen3-Coder-30B-A3B-Instruct-BF16-00001-of-00002.gguf ...
```
*Note: We prefer Option A (dedicated folder) to keep things organized, but Option B is great for quick tests.*

### 4. Run a Model

> [!TIP]
> You should **always** use `-fa 1` (Flash Attention). This significantly improves performance and memory utilization on the R9700.

Use **`llama-cli`** for running models directly in your terminal—ideal for quick tests, benchmarking, or chatting without leaving the shell.

Use **`llama-server`** to start an OpenAI-compatible API server. This allows you to connect third-party UIs (like Open WebUI), use the built-in web interface, or build your own applications using standard libraries.

**Run it (CLI Chat):**
```bash
llama-cli -ngl 999 -fa 1 \
  -m models/qwen3-coder-30B-A3B/BF16/Qwen3-Coder-30B-A3B-Instruct-BF16-00001-of-00002.gguf \
  -p "Write a R9700 toolkit haiku."
```

**Or run as Server (API + Web UI):**
```bash
llama-server -m models/qwen3-coder-30B-A3B/BF16/Qwen3-Coder-30B-A3B-Instruct-BF16-00001-of-00002.gguf \
  -c 8192 -ngl 999 -fa 1
```

---

## 📖 Detailed Guide

### Managing Toolboxes

#### Ubuntu Users (Distrobox)
If you are on Ubuntu, use Distrobox to ensure proper GPU access:
```bash
distrobox create -n r9700-llama-rocm-10.0 \
  --image docker.io/kyuz0/amd-r9700-toolboxes:rocm-10.0 \
  --additional-flags "--device /dev/kfd --device /dev/dri --group-add video --group-add render --security-opt seccomp=unconfined"
distrobox enter r9700-llama-rocm-10.0
```

#### Updating Toolboxes
AI Toolbox Cockpit is the recommended update path. If you created Toolbx containers manually, the repository script can pull the latest images and recreate them:
```bash
# Refresh all toolboxes
./refresh-toolboxes.sh all

# Or refresh specific ones
./refresh-toolboxes.sh r9700-llama-vulkan-radv r9700-llama-rocm-10.0
```

## 📦 Architecture & Containers

### Backends
*   **Vulkan**: Cross-platform, very stable.
    *   **RADV (Mesa)**: Best compatibility.
    *   **ROCmFPX**: Custom Vulkan build for ROCmFP3/FP4/FP6/FP8 model formats.
*   **ROCm**: AMD's compute stack, available as the stable ROCm 10.0 Core SDK and the latest TheRock nightly.

## ⚡ Performance & Planning

### Benchmarks
Check the [Interactive Benchmark Viewer](https://kyuz0.github.io/amd-r9700-ai-toolboxes/) or [docs/benchmarks.md](docs/benchmarks.md) to see performance numbers.

### VRAM Estimator
Use the included script to estimate memory usage for models + context. This helps avoid OOM errors.
```bash
gguf-vram-estimator.py models/my-model.gguf --contexts 4096 32768
```
See [docs/vram-estimator.md](docs/vram-estimator.md) for more details.

##  References

*   [Llama.cpp GitHub Repository](https://github.com/ggerganov/llama.cpp)
*   [AMD RDNA™ 4 Architecture](https://www.amd.com/en/products/graphics/rdna-architecture.html)
