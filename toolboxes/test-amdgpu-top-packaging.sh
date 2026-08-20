#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FETCHER="${SCRIPT_DIR}/fetch-amdgpu-top-rpm.sh"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

test -x "${FETCHER}" || fail "missing executable fetch-amdgpu-top-rpm.sh"

test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT

rpm_path="${test_root}/amdgpu_top.rpm"
"${FETCHER}" "${rpm_path}"
test -s "${rpm_path}" || fail "fetcher did not create a non-empty RPM"

for dockerfile in \
  Dockerfile.vulkan-radv \
  Dockerfile.rocm-7.14 \
  Dockerfile.therock-nightly; do
  path="${SCRIPT_DIR}/${dockerfile}"
  grep -Fq '/tmp/fetch-amdgpu-top-rpm /tmp/amdgpu_top.rpm' "${path}" ||
    fail "${dockerfile} does not fetch the pinned amdgpu_top RPM"
  grep -Fq 'COPY --from=builder /tmp/amdgpu_top.rpm /tmp/amdgpu_top.rpm' "${path}" ||
    fail "${dockerfile} does not copy the verified RPM into the runtime stage"
  grep -Fq '/tmp/amdgpu_top.rpm' "${path}" ||
    fail "${dockerfile} does not install the RPM"
done

printf 'PASS: pinned amdgpu_top packaging contract\n'
