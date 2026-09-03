# syntax=docker/dockerfile:1.7
# SPDX-License-Identifier: Apache-2.0
#
# Model-specific R9V runtime for Qwen3.8 Flash Next on two Radeon AI PRO
# R9700 GPUs. The R9V source graph is pinned; only its qualified ROCm 7.14
# base is deliberately replaced with AMD's ROCm 10.0.0 development image.

ARG ROCM_BASE=docker.io/rocm/dev-ubuntu-24.04:10.0.0-full@sha256:a90cf047f615abe70fbef83c64def0a2d549ef37a39c8ea545430aba4981b374
ARG R9V_REPO=https://github.com/Dyluhn/R9V.git
ARG R9V_REVISION=30e5a743eb7de4e40432ccb694cf8149804ba653
ARG GFX_ARCH=gfx1201
ARG TORCH_VERSION=2.11.0
ARG TRITON_VERSION=3.6.0
ARG TORCHVISION_VERSION=0.24.1
ARG AITER_VERSION=0.1.19
ARG FLYDSL_VERSION=0.2.4
ARG TRANSFORMERS_VERSION=5.14.1
ARG R9V_VLLM_VERSION=0.26.1rc0+r9v.g4b20917386dc


FROM ubuntu:24.04 AS r9v-source

ARG R9V_REPO
ARG R9V_REVISION

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none --no-checkout "${R9V_REPO}" /src/r9v \
 && git -C /src/r9v fetch --depth 1 origin "${R9V_REVISION}" \
 && git -C /src/r9v checkout --detach FETCH_HEAD \
 && test "$(git -C /src/r9v rev-parse HEAD)" = "${R9V_REVISION}" \
 && git -C /src/r9v submodule update --init --recursive --depth 1 \
      kernels/r9v-gfx1201 vendor/vllm vendor/vllm-gguf-plugin \
 && test "$(git -C /src/r9v/vendor/vllm rev-parse HEAD)" = \
      4b20917386dcdfb619ee62ff24c45efeae176fdf \
 && test "$(git -C /src/r9v/vendor/vllm-gguf-plugin rev-parse HEAD)" = \
      09b1199015c6b45de5c13dc4b36857ce27d9b0cd \
 && test "$(git -C /src/r9v/kernels/r9v-gfx1201 rev-parse HEAD)" = \
      7905d9e0a3323411ef5d6dfb2f356061a9a491e3


FROM ${ROCM_BASE} AS wheel-builder

ARG GFX_ARCH
ARG TORCH_VERSION
ARG TRITON_VERSION
ARG TORCHVISION_VERSION
ARG AITER_VERSION
ARG R9V_VLLM_VERSION
ARG MAX_JOBS=8

ENV DEBIAN_FRONTEND=noninteractive \
    PYTORCH_ROCM_ARCH=${GFX_ARCH} \
    ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm \
    USE_ROCM=1 \
    USE_CUDA=0 \
    MAX_JOBS=${MAX_JOBS} \
    CMAKE_BUILD_PARALLEL_LEVEL=${MAX_JOBS}

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git python3.12-venv build-essential ccache pkg-config \
      libdrm-dev libnuma-dev libelf-dev \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/py
ENV PATH=/opt/py/bin:$PATH

RUN pip install -U pip wheel setuptools "setuptools-scm>=8.0" "cmake<4" \
      ninja pybind11 numpy pyyaml typing_extensions cffi requests \
 && mkdir -p /wheels

# Match R9V's source build, targeting only gfx1201. ROCm 10.0 is the sole
# intentional divergence from the pinned upstream recipe.
RUN git clone --depth 1 -b v${TORCH_VERSION} --recurse-submodules \
      --shallow-submodules https://github.com/pytorch/pytorch.git /src/pytorch \
 && cd /src/pytorch \
 && pip install -r requirements.txt \
 && python tools/amd_build/build_amd.py \
 && USE_MAGMA=0 USE_MKLDNN=1 BUILD_TEST=0 USE_NCCL=1 USE_RCCL=1 \
      USE_FLASH_ATTENTION=0 USE_MEM_EFF_ATTENTION=0 USE_AOTRITON=0 \
      PYTORCH_BUILD_VERSION=${TORCH_VERSION}+rocm10.0 \
      PYTORCH_BUILD_NUMBER=1 \
      python setup.py bdist_wheel \
 && cp dist/*.whl /wheels/ \
 && pip install dist/*.whl \
 && rm -rf /src/pytorch

RUN git clone --depth 1 -b v${TRITON_VERSION} \
      https://github.com/triton-lang/triton.git /src/triton \
 && cd /src/triton \
 && pip wheel --no-build-isolation --no-deps . -w /wheels \
 && pip install /wheels/triton-*.whl \
 && rm -rf /src/triton

RUN git clone --depth 1 -b v${TORCHVISION_VERSION} \
      https://github.com/pytorch/vision.git /src/vision \
 && cd /src/vision \
 && FORCE_CUDA=1 USE_ROCM=1 \
      pip wheel --no-build-isolation --no-deps . -w /wheels \
 && rm -rf /src/vision

RUN git clone --recursive --shallow-submodules -b v${AITER_VERSION} \
      https://github.com/ROCm/aiter.git /src/aiter \
 && cd /src/aiter \
 && GPU_ARCHS=${GFX_ARCH} PREBUILD_KERNELS=0 \
      SETUPTOOLS_SCM_PRETEND_VERSION=${AITER_VERSION} \
      pip wheel --no-build-isolation --no-deps . -w /wheels \
 && pip install /wheels/*aiter-*.whl \
 && rm -rf /src/aiter

COPY --from=r9v-source /src/r9v/vendor/vllm /src/vllm
RUN cd /src/vllm \
 && python use_existing_torch.py \
 && python -m pip install "setuptools-rust>=1.9" \
 && VLLM_TARGET_DEVICE=rocm \
      SETUPTOOLS_SCM_PRETEND_VERSION=${R9V_VLLM_VERSION} \
      VLLM_VERSION_OVERRIDE=${R9V_VLLM_VERSION} \
      python -m pip wheel --no-build-isolation --no-deps . \
        --wheel-dir /wheels


FROM ${ROCM_BASE}

ARG GFX_ARCH
ARG AITER_VERSION
ARG FLYDSL_VERSION
ARG TRANSFORMERS_VERSION
ARG R9V_VLLM_VERSION
ARG R9V_REVISION

LABEL org.opencontainers.image.title="R9V Qwen3.8 Flash Next ROCm 10.0 toolbox" \
      org.opencontainers.image.description="Model-specific dual-R9700 R9V runtime ported to ROCm 10.0" \
      org.opencontainers.image.source="https://github.com/Dyluhn/R9V" \
      org.opencontainers.image.revision="${R9V_REVISION}" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash ca-certificates curl g++ git less libgomp1 libnuma-dev numactl \
      procps python3 python3.12 python3.12-dev python3.12-venv sudo vim \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/r9v
ENV VIRTUAL_ENV=/opt/r9v \
    PATH=/opt/r9v/bin:/opt/rocm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm \
    HIP_PLATFORM=amd \
    VLLM_TARGET_DEVICE=rocm \
    PYTORCH_ROCM_ARCH=${GFX_ARCH} \
    HIP_ARCHITECTURES=${GFX_ARCH} \
    AMDGPU_TARGETS=${GFX_ARCH} \
    GPU_ARCHS=${GFX_ARCH} \
    HSA_NO_SCRATCH_RECLAIM=1 \
    SAFETENSORS_FAST_GPU=1 \
    TOKENIZERS_PARALLELISM=false \
    PYTHONDONTWRITEBYTECODE=1 \
    RADIANCE_USE_R4D=0 \
    RADIANCE_USE_R4D_AR=0 \
    RADIANCE_USE_R4D_GDN=0 \
    RADIANCE_USE_R4D_AR_QUANT=0

COPY --from=wheel-builder /wheels /wheels
RUN python -m pip install --upgrade pip wheel setuptools \
 && python -m pip install --no-deps \
      /wheels/torch-*.whl /wheels/triton-*.whl \
      /wheels/torchvision-*.whl /wheels/*aiter-*.whl \
 && python -m pip install /wheels/vllm-*.whl \
      "transformers==${TRANSFORMERS_VERSION}" \
 && python -m pip install /opt/rocm/share/amd_smi pillow pybind11 \
      "flydsl==${FLYDSL_VERSION}" \
 && python -m pip check \
 && WANT_VLLM=${R9V_VLLM_VERSION} WANT_AITER=${AITER_VERSION} \
      WANT_FLYDSL=${FLYDSL_VERSION} \
      WANT_TRANSFORMERS=${TRANSFORMERS_VERSION} \
      python -c 'import importlib.metadata as m, os, torch; \
v=m.version("vllm"); a=m.version("amd-aiter"); f=m.version("flydsl"); t=m.version("transformers"); \
assert v.startswith(os.environ["WANT_VLLM"]), (v, os.environ["WANT_VLLM"]); \
assert a == os.environ["WANT_AITER"], (a, os.environ["WANT_AITER"]); \
assert f == os.environ["WANT_FLYDSL"], (f, os.environ["WANT_FLYDSL"]); \
assert t == os.environ["WANT_TRANSFORMERS"], (t, os.environ["WANT_TRANSFORMERS"]); \
assert torch.version.hip and torch.version.hip.startswith("7.15"), torch.version.hip; \
print("torch", torch.__version__, "hip", torch.version.hip, "vllm", v, "amd-aiter", a, "flydsl", f, "transformers", t)'

# The ROCm Core SDK 10.0 packages currently expose HIP API/compiler version
# 7.15. Validate both identities so the source-built PyTorch check does not
# confuse the component version with the ROCm platform release.
RUN dpkg-query -W -f='${Version}\n' amdrocm-base10.0 | grep -Eq '^10\.0\.0-'

COPY --from=r9v-source /src/r9v/vendor/vllm-gguf-plugin /opt/r9v-src/vllm-gguf-plugin
RUN VLLM_GGUF_PLUGIN_LOCAL_VERSION_SUFFIX=r9v \
      python -m pip install --no-build-isolation --no-cache-dir \
        /opt/r9v-src/vllm-gguf-plugin

COPY --from=r9v-source /src/r9v/kernels/r9v-gfx1201 /opt/r9v-src/kernels
RUN VLLM_GGUF_PLUGIN_CSRC=/opt/r9v-src/vllm-gguf-plugin/vllm_gguf_plugin/csrc \
      QWEN38_DENSE_MMVQ_BUILD_DIR=/opt/r9v-build/dense \
      python /opt/r9v-src/kernels/dense_mmvq_hip/build_extension.py \
 && VLLM_GGUF_PLUGIN_CSRC=/opt/r9v-src/vllm-gguf-plugin/vllm_gguf_plugin/csrc \
      python /opt/r9v-src/kernels/tiered_iq_moe_hip/build_extension.py \
        --build-directory /opt/r9v-build/tiered \
        --variants auto,u2,u5,u10,reuse3,reuse3v2 \
 && QWEN38_GDN_BUILD_DIR=/opt/r9v-build/gdn \
      python /opt/r9v-src/kernels/fused_gdn_mtp_hip/build_extension.py \
 && install -d /opt/r9v/kernels \
 && install -m 0755 /opt/r9v-build/dense/qwen38_dense_mmvq_hip.so \
      /opt/r9v/kernels/ \
 && install -m 0755 /opt/r9v-build/tiered/qwen38_tiered_iq_moe_hip.so \
      /opt/r9v/kernels/ \
 && install -m 0755 /opt/r9v-build/gdn/qwen38_fused_gdn_mtp_hip.so \
      /opt/r9v/kernels/ \
 && rm -rf /opt/r9v-build /opt/r9v-src /wheels /root/.cache

COPY --from=r9v-source /src/r9v/tools/prepare_ple.py /usr/local/libexec/r9v/prepare_ple.py

RUN chmod 0755 /usr/local/libexec/r9v/prepare_ple.py \
 && python -c 'import importlib.metadata as m; assert m.version("vllm-gguf-plugin").startswith("0.0.5")' \
 && test -s /opt/r9v/kernels/qwen38_dense_mmvq_hip.so \
 && test -s /opt/r9v/kernels/qwen38_tiered_iq_moe_hip.so \
 && test -s /opt/r9v/kernels/qwen38_fused_gdn_mtp_hip.so

ENV QWEN38_DENSE_MMVQ_HIP_SO=/opt/r9v/kernels/qwen38_dense_mmvq_hip.so \
    QWEN38_TIERED_IQ_MOE_HIP_SO=/opt/r9v/kernels/qwen38_tiered_iq_moe_hip.so \
    QWEN38_FUSED_GDN_MTP_HIP_SO=/opt/r9v/kernels/qwen38_fused_gdn_mtp_hip.so

CMD ["/bin/bash"]
