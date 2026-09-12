# Serialized expert-loading patch

This is a project-specific change to the upstream R9V GGUF plugin. Here,
“overlay” means a patch applied to the installed Python loader during the
Docker build.

## Why it exists

On the tested two-R9700 / 64 GB RAM host, both GPU workers created approximately
27.7 GiB temporary expert-weight buffers at the same time. Available host RAM
fell to 1.8 GiB and the memory guard stopped startup. Serializing this loading
phase, together with the separate Torch SHM library-path fix, allowed startup
to complete with at least 17.2 GiB available RAM (September 2026 measurements).

## What changes

- `install-overlay.py` wraps target `model.load_weights` and hot-expert cache
  materialization/compaction in a shared lock, then installs `serialized_load.py`.
- One local tensor-parallel worker completes that phase before the other enters.
  Worker order is not fixed.
- Model initialization, generic postprocessing, PLE and MTP draft loading remain
  outside the lock. Weights, inference kernels and parallel inference are unchanged.

The pinned loading block was audited for inter-worker collectives: none were
found inside the locked region. Do not expand that region without checking
again; a collective could wait forever for the worker blocked on the lock.

## Controls and review

The image enables `R9V_SERIALIZE_EXPERT_LOAD=1`. Setting it to `0` bypasses the
lock and restores overlapping loading, including the original RAM-pressure risk.
The lock applies only to the target model with a tiered-expert manifest.

Both workers must share `R9V_EXPERT_LOAD_LOCK_PATH`, default
`/cache/r9v-expert-load.lock`. **Never delete or replace that file during startup.**
The lock is released on exceptions and process death; an existing unlocked file
does not block the next startup. Log events record waiting, acquisition, release
and failures.

The installer checks the exact upstream loader SHA256 and expected patch sites;
it rejects source drift or an already-patched loader. Preview without modifying:

```bash
python3 toolboxes/r9v/serialized-load/install-overlay.py --review \
  /path/to/pinned/vllm_gguf_plugin/loader.py
```

The image records original, patched and helper hashes in
`/opt/r9v-manifests/serialized-expert-load.json`. The expected upstream revision
and SHA256 are in the installer. Upstream updates require a fresh review of the
loading block, memory lifetime and collective boundaries.
