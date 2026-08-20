#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_AMDGPU_TOP_VERSION="0.11.5"
readonly DEFAULT_AMDGPU_TOP_SHA256="ef224f5d1c8e7621a2f309c3d465d05a18c4c660d48da5edc215c7c4e6d53e71"

output_path="${1:?usage: fetch-amdgpu-top-rpm.sh OUTPUT_PATH}"
version="${AMDGPU_TOP_VERSION:-${DEFAULT_AMDGPU_TOP_VERSION}}"

if [[ "${version}" != "${DEFAULT_AMDGPU_TOP_VERSION}" && -z "${AMDGPU_TOP_SHA256:-}" ]]; then
  printf 'AMDGPU_TOP_SHA256 is required when overriding AMDGPU_TOP_VERSION\n' >&2
  exit 2
fi

sha256="${AMDGPU_TOP_SHA256:-${DEFAULT_AMDGPU_TOP_SHA256}}"
if [[ ! "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'invalid AMDGPU_TOP_VERSION: %s\n' "${version}" >&2
  exit 2
fi
if [[ ! "${sha256}" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'invalid AMDGPU_TOP_SHA256\n' >&2
  exit 2
fi

url="https://github.com/Umio-Yasuno/amdgpu_top/releases/download/v${version}/amdgpu_top-${version}-1.x86_64.rpm"
partial_path="${output_path}.part.$$"
trap 'rm -f -- "${partial_path}"' EXIT

curl --fail --location --silent --show-error \
  --connect-timeout 15 --max-time 300 \
  --retry 4 --retry-delay 2 --retry-all-errors \
  --output "${partial_path}" "${url}"
printf '%s  %s\n' "${sha256}" "${partial_path}" | sha256sum --check --status
mv -- "${partial_path}" "${output_path}"

