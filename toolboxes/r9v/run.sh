#!/usr/bin/env bash
# Trusted shell configuration may be supplied through R9V_CONFIG_FILE.
set -euo pipefail
if [[ -n ${R9V_CONFIG_FILE:-} ]]; then
  set -a
  source "$R9V_CONFIG_FILE"
  set +a
fi
image=${R9V_IMAGE:-docker.io/kyuz0/amd-r9700-toolboxes:r9v-rocm-10.0}
name=${R9V_CONTAINER_NAME:-r9700-r9v}
model=${R9V_MODEL_DIR:-$HOME/models/R9V-Qwen3.8-IQ4_XS}
ple=${R9V_PLE_PATH:-$HOME/r9v-data/per_layer_token_embd.iq4_nl.bin}
cache=${R9V_CACHE_DIR:-$HOME/r9v-data/cache-toolbox-rocm10}
port=${R9V_HOST_PORT:-8004}
[[ $port =~ ^[0-9]+$ && ${#port} -le 5 ]] && ((10#$port > 0 && 10#$port < 65536)) || {
  echo 'R9V_HOST_PORT must be a TCP port between 1 and 65535.' >&2; exit 2;
}
for path in "$model" "$ple" "$cache"; do
  [[ $path == /* && $path != *:* && $path != *$'\n'* ]] || {
    echo 'Model, PLE and cache paths must be absolute, without colons/newlines.' >&2; exit 2;
  }
done
for required in "$model"/target/Qwen3.8-Flash-Next-UD-IQ4_XS-0000{1,2,3}-of-00003.gguf \
  "$model/metadata/config.json" "$model/mtp/config.json" "$model/mtp/model.safetensors" \
  "$model/vision/mmproj-Qwen3.8-Flash-Next-Q8_0.gguf" \
  "$model/manifests/hot-manifest-q4-vision-128k-multiprompt-r1-lru16-neutral.json" "$ple"; do
  [[ -r $required ]] || { echo "Missing/unreadable model artifact: $required" >&2; exit 1; }
done
[[ $(stat -c %s "$ple") == 28800138240 ]] || { echo 'Unexpected PLE file size.' >&2; exit 1; }
command -v podman >/dev/null
[[ $(podman info --format '{{.Host.Security.Rootless}}') == true ]] || {
  echo 'Run this helper as your normal user with rootless Podman.' >&2; exit 1;
}
if podman container exists "$name"; then
  echo "Container already exists: $name. Stop/remove it explicitly before relaunch." >&2; exit 1
fi
[[ -r /dev/kfd && -w /dev/kfd && -d /dev/dri ]] || {
  echo 'This user needs read/write access to /dev/kfd and access to /dev/dri.' >&2; exit 1;
}
mkdir -p "$cache"
env_args=()
# Export profile overrides explicitly; do not forward unrelated host variables.
while IFS= read -r key; do
  [[ $key == R9V_* ]] && env_args+=(--env "$key=${!key}")
done < <(compgen -e)
podman --runtime crun run --detach --pull=never --name "$name" \
  --user 0:0 --group-add keep-groups --device /dev/kfd --device /dev/dri \
  --ipc host --security-opt seccomp=unconfined --security-opt label=disable \
  --publish "127.0.0.1:$port:8000" \
  --volume "$model:/models:ro" --volume "$ple:/ple/per_layer_token_embd.iq4_nl.bin:ro" \
  --volume "$cache:/cache" "${env_args[@]}" "$image" r9v-serve "$@"
printf 'Started %s. Logs: podman logs -f %s\nAPI: http://127.0.0.1:%s/v1\n' "$name" "$name" "$port"
