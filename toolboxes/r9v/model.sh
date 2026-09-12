#!/usr/bin/env bash
set -euo pipefail
tools=/opt/r9v-src/tools
descriptor=/opt/r9v-src/packages/models/qwen38-flash-next/ud-iq4-xs--mtp-blockfp8--mmproj-q8/package.json
case ${1:-help} in
  download)
    shift
    exec python "$tools/fetch_package.py" "$descriptor" --model-dir /models "$@"
    ;;
  verify)
    exec python "$tools/verify_package.py" "$descriptor" --model-dir /models --hash
    ;;
  prepare)
    python "$tools/prepare_ple.py" /models/target/*.gguf \
      --output /ple/per_layer_token_embd.iq4_nl.bin
    printf '%s  %s\n' dd55c28902f38cd88134b2a569c51282c5ffce30080487e1a645740115c56cc3 \
      /ple/per_layer_token_embd.iq4_nl.bin | sha256sum --check
    ;;
  *)
    echo 'Usage: r9v-model download [--accept-model-license] | verify | prepare'
    echo 'Mount the model directory at /models and the PLE directory at /ple.'
    [[ ${1:-help} == help || ${1:-help} == --help ]]
    ;;
esac
