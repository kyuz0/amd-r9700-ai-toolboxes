# Current R9V on two R9700 cards

This profile supports Qwen3.8 Flash Next IQ4_XS with FP8 MTP-2, one sequence and a 67,840-token context on two Radeon AI PRO R9700 32 GB cards. Qualification used 64 GB host RAM, 8 GiB swap and NVMe storage. PLE stays disk-backed. Startup takes several minutes.

The manual R9V workflow resolves the latest stable upstream release at build time and follows that release's vLLM/GGUF-plugin/kernel submodules. ROCm 10, Torch 2.11 and Triton 3.8 form the compatible runtime stack. The image includes serialized expert loading for 64 GB hosts; its reviewed loader contract fails the build if upstream changes that critical section. Actual sources and installed versions are recorded under `/opt/r9v-manifests` and in the workflow artifact. Image bases use mutable tags.


## Build and install

From this repository's root, build inside Podman:

```bash
podman build --layers --memory=24g --build-arg MAX_JOBS=4 \
  -f toolboxes/Dockerfile.r9v-rocm-10.0-latest \
  -t docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0-current toolboxes
```

In AI Toolbox Cockpit, select **R9700 → R9V → R9V · ROCm 10 · 64 GB host** and pull the rolling public image. The profile uses the defaults below; choose the intended pair of R9700 devices.

| Setting | Qualified value |
| --- | --- |
| Target / draft | IQ4_XS / FP8 MTP-2 |
| Tensor parallel / sequences | 2 GPUs / 1 sequence |
| Context / prefill batch | 67,840 / 1,024 tokens |
| KV allocation | 1,748,799,488 bytes per GPU |
| Expert cache / offload | 16 slots / 112.5 logical GB per device |
| PLE / scheduling | SSD-backed / synchronous |

## Models and launch

In **Models → R9V**, use **Download / Repair** for the pinned [IQ4_XS package](https://huggingface.co/Dyluhn/Qwen3.8-Flash-Next-R9V-IQ4_XS/tree/bf836f0c20b6c92fcad4226ad3115eb8a19f7582), then **Prepare PLE**. Existing verified package and PLE files can be reused. Allow about 118 GiB for the package and PLE, plus the image and compilation caches.

In **Server Mode → R9V**, select the current R9V toolbox and package, retain the qualified settings, and use a separate compilation-cache directory. The tested profile covers text serving with MTP-2. Model weights and the PLE file remain separate from the container image.
