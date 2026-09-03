# R9V Qwen3.8 Flash Next toolbox

The `r9v-qwen38-rocm-10.0` image is a model-specific R9V runtime for exactly
two Radeon AI PRO R9700 (`gfx1201`) GPUs. It preserves R9V's pinned vLLM fork,
GGUF plugin, three kernel families, Qwen profile, placement policy, MTP2, and
128K context. The intentional porting change is ROCm 10.0.0 in place of the
upstream-qualified ROCm 7.14.0 base.

AMD's ROCm Core SDK 10.0.0 package set exposes HIP component version 7.15.
Image validation therefore checks the `amdrocm-base10.0` package for the ROCm
platform release and `torch.version.hip` for the corresponding HIP component;
the two version strings are intentionally different.

The image does not contain model weights. The Qwen package uses the Qwen
Community License 1.0; review and accept that license before downloading it.
Plan for about 150 GiB free SSD space for the 90.36 GiB package, 26.82 GiB
derived PLE payload, and working/cache headroom. Upstream qualified the profile
with 128 GB host RAM. Smaller hosts are allowed but unqualified and have less
page cache for the SSD-backed PLE.

## Create the toolbox

```bash
toolbox create r9700-r9v-qwen38-rocm-10.0 \
  --image docker.io/kyuz0/amd-r9700-toolboxes:r9v-qwen38-rocm-10.0 \
  -- --device /dev/dri --device /dev/kfd \
  --group-add video --group-add render --group-add sudo \
  --ipc host --security-opt seccomp=unconfined
toolbox enter r9700-r9v-qwen38-rocm-10.0
```

Device order is semantic. `R9V_VISIBLE_DEVICES=0,1` means that HIP device 0 is
tensor-parallel rank 0 and device 1 is rank 1; rank 1 receives the larger
static expert placement and a 16-slot dynamic cache. Confirm the KFD order on
the host before changing it.

## Download and run the pinned model package

Use AI Toolbox Cockpit's R9V Models panel to accept the model license, download
R9V's immutable package revision, verify its artifacts, and derive the PLE
payload. The R9V Server panel owns the exact device order, mounts, environment,
and vLLM launch arguments.

```bash
pipx install git+https://github.com/kyuz0/ai-toolbox-cockpit.git
ai-toolbox-cockpit
```

The server defaults to `127.0.0.1:8004`. Test it from another terminal:

```bash
curl -fsS http://127.0.0.1:8004/health
curl -fsS http://127.0.0.1:8004/v1/models
curl -fsS http://127.0.0.1:8004/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-flash-next","max_tokens":32,"messages":[{"role":"user","content":"Say hello."}]}'
```

The image carries the runtime and R9V's upstream PLE extractor only. Cockpit is
the source of truth for host-side package lifecycle and launch policy. Changing
topology, placement, MTP, cache, or kernel values forfeits upstream's reported
benchmark comparison.

## Source pins

- R9V: `30e5a743eb7de4e40432ccb694cf8149804ba653`
- vLLM fork: `4b20917386dcdfb619ee62ff24c45efeae176fdf`
- GGUF plugin: `09b1199015c6b45de5c13dc4b36857ce27d9b0cd`
- R9V kernels: `7905d9e0a3323411ef5d6dfb2f356061a9a491e3`
- ROCm image: `docker.io/rocm/dev-ubuntu-24.04:10.0.0-full` at digest
  `sha256:a90cf047f615abe70fbef83c64def0a2d549ef37a39c8ea545430aba4981b374`

R9V source and original kernels are Apache-2.0; GGUF quant primitives retain
their MIT notices. Model artifacts remain separately licensed under Qwen
Community License 1.0.
