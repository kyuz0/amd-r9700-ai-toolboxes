#!/usr/bin/env bash
set -uo pipefail

MODEL_DIR="$(realpath ~/models)"
RESULTDIR="results"
mkdir -p "$RESULTDIR"

# Pick exactly one .gguf per model: either
#  - any .gguf without "-000*-of-" (single-file models)
#  - or the first shard "*-00001-of-*.gguf"
mapfile -t MODEL_PATHS < <(
  find "$MODEL_DIR" -type f -name '*.gguf' \
    \( -name '*-00001-of-*.gguf' -o -not -name '*-000*-of-*.gguf' \) \
    | sort
)

if (( ${#MODEL_PATHS[@]} == 0 )); then
  echo "❌ No models found under $MODEL_DIR – check your paths/patterns!"
  exit 1
fi

echo "Found ${#MODEL_PATHS[@]} model(s) to bench:"
for p in "${MODEL_PATHS[@]}"; do
  echo "  • $p"
done
echo

declare -A CMDS=(
  [rocm6_4_4]="toolbox run -c llama-rocm-6.4.4 -- /usr/local/bin/llama-bench"
  [rocm6_4_4-rocwmma]="toolbox run -c llama-rocm-6.4.4-rocwmma -- /usr/local/bin/llama-bench"
  [rocm7.1.1]="toolbox run -c llama-rocm-7.1.1 -- /usr/local/bin/llama-bench"
  [rocm7.1.1-rocwmma]="toolbox run -c llama-rocm-7.1.1-rocwmma -- /usr/local/bin/llama-bench"
  [rocm-7-nightly]="toolbox run -c llama-rocm-7-nightly -- /usr/local/bin/llama-bench"
  [rocm-7-nightly-rocwmma]="toolbox run -c llama-rocm-7-nightly-rocwmma -- /usr/local/bin/llama-bench"
  [rocm-7.9]="toolbox run -c llama-rocm-7.9 -- /usr/local/bin/llama-bench"
  [rocm-7.9-rocwmma]="toolbox run -c llama-rocm-7.9-rocwmma -- /usr/local/bin/llama-bench"
  [vulkan_amdvlk]="toolbox run -c llama-vulkan-amdvlk -- /usr/sbin/llama-bench"
  [vulkan_radv]="toolbox run -c llama-vulkan-radv -- /usr/sbin/llama-bench"
)

get_hblt_modes() {
  local env="$1"
  if [[ "$env" == rocm* ]]; then
    printf '%s\n' default off
  else
    printf '%s\n' default
  fi
}

for MODEL_PATH in "${MODEL_PATHS[@]}"; do
  MODEL_NAME="$(basename "$MODEL_PATH" .gguf)"

  if [[ "$MODEL_PATH" == *"-00001-of-"* ]]; then
    # Multi-shard model: sum all shards
    DIR="$(dirname "$MODEL_PATH")"
    BASE="$(basename "$MODEL_PATH")"
    PATTERN="${BASE/-00001-of-/-*-of-}"
    MODEL_SIZE=$(find "$DIR" -maxdepth 1 -name "$PATTERN" -exec stat -c%s {} + | awk '{s+=$1} END {print s}')
  else
    # Single-file model
    MODEL_SIZE=$(stat -c%s "$MODEL_PATH")
  fi

  # Threshold: 30 GiB = 32212254720 bytes. Using 32000000000 as a safe cutoff.
  if (( MODEL_SIZE > 32000000000 )); then
    GPU_DEVICES="0,1"
    GPU_SUFFIX="__dual"
  else
    GPU_DEVICES="0"
    GPU_SUFFIX="__single"
  fi

  for ENV in "${!CMDS[@]}"; do
    CMD="${CMDS[$ENV]}"
    mapfile -t HBLT_MODES < <(get_hblt_modes "$ENV")

    for MODE in "${HBLT_MODES[@]}"; do
      BASE_SUFFIX=""
      CMD_EFFECTIVE="$CMD"

      if [[ "$ENV" == rocm* ]]; then
        if [[ "$MODE" == off ]]; then
          BASE_SUFFIX="__hblt0"
          CMD_EFFECTIVE="${CMD_EFFECTIVE/-- /-- env HIP_VISIBLE_DEVICES=$GPU_DEVICES ROCBLAS_USE_HIPBLASLT=0 }"
        else
          CMD_EFFECTIVE="${CMD_EFFECTIVE/-- /-- env HIP_VISIBLE_DEVICES=$GPU_DEVICES ROCBLAS_USE_HIPBLASLT=1 }"
        fi
      fi

      # run twice: baseline and with flash attention
      for FA in 1; do
        SUFFIX="$BASE_SUFFIX"
        EXTRA_ARGS=()
        if (( FA == 1 )); then
          SUFFIX="${SUFFIX}__fa1"
          EXTRA_ARGS=( -fa 1 )
        fi

        for CTX in default longctx16384 longctx32768; do
          CTX_SUFFIX=""
          CTX_ARGS=()
          if [[ "$CTX" == longctx32768 ]]; then
            CTX_SUFFIX="__longctx32768"
            CTX_ARGS=( -p 2048 -n 32 -d 32768 )
            if [[ "$ENV" == *vulkan* ]]; then
              CTX_ARGS+=( -ub 512 )
            else
              CTX_ARGS+=( -ub 2048 )
            fi
          elif [[ "$CTX" == longctx16384 ]]; then
            CTX_SUFFIX="__longctx16384"
            CTX_ARGS=( -p 2048 -n 32 -d 16384 )
            if [[ "$ENV" == *vulkan* ]]; then
              CTX_ARGS+=( -ub 512 )
            else
              CTX_ARGS+=( -ub 2048 )
            fi
          fi

          OUT="$RESULTDIR/${MODEL_NAME}__${ENV}${SUFFIX}${CTX_SUFFIX}${GPU_SUFFIX}.log"
          CTX_REPS=3
          if [[ "$CTX" == longctx* ]]; then
            CTX_REPS=1
          fi

          if [[ -s "$OUT" ]]; then
            echo "⏩ Skipping [${ENV}] ${MODEL_NAME}${SUFFIX}${CTX_SUFFIX:+ ($CTX_SUFFIX)}, log already exists at $OUT"
            continue
          fi

          FULL_CMD=( $CMD_EFFECTIVE -ngl 99 -m "$MODEL_PATH" "${EXTRA_ARGS[@]}" "${CTX_ARGS[@]}" -r "$CTX_REPS" )

          printf "\n▶ [%s] %s%s%s\n" "$ENV" "$MODEL_NAME" "${SUFFIX:+ $SUFFIX}" "${CTX_SUFFIX:+ $CTX_SUFFIX}"
          printf "  → log: %s\n" "$OUT"
          printf "  → cmd: %s\n\n" "${FULL_CMD[*]}"

          if ! "${FULL_CMD[@]}" >"$OUT" 2>&1; then
            status=$?
            echo "✖ ! [${ENV}] ${MODEL_NAME}${SUFFIX}${CTX_SUFFIX:+ $CTX_SUFFIX} failed (exit ${status})" >>"$OUT"
            echo "  * [${ENV}] ${MODEL_NAME}${SUFFIX}${CTX_SUFFIX:+ $CTX_SUFFIX} : FAILED"
          fi
        done
      done
    done
  done
done
