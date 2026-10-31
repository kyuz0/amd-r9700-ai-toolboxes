# Experimental four-R9700 DeepSeek toolboxes

These source recipes package three distinct inference engines for Radeon AI PRO R9700 (`gfx1201`). They retain a compiler/runtime environment and an interactive shell for Toolbx/Distrobox, plus the native engine executables.

| Engine | Source channel | ROCm | Native format | Intended profile |
| --- | --- | --- | --- | --- |
| Affinity | Maintained `neuromaniacMD/affinity` `v4-fixes` branch with the included HTTP-v2 overlay | 10.1 | `.aff`, matched `.dspark.aff`, tokenizer JSON | DeepSeek-V4-Flash-0731, four GPUs, GPU-resident target experts, target-only or DSpark, one sequence |
| hipfire | Latest stable `warpfront/hipfire` release | 10.1 | MQ2R | DeepSeek-V4-Flash-0731, four GPUs, target-only, F32 KV |
| Strata | Latest stable `Niko1221/Strata` release | 10.1 | GSQ-RCO IQ2_XXS GGUF, Engram, auxiliary sidecars and native metadata | DeepSeek-V4.1-Flash-1017, four GPUs, six-expert routing with expert offload, target-only or DSpark, one sequence |

The workflow **Build quad R9700 engine candidates** resolves and records the actual source commit. It can build all engines or one engine, with the latest stable source or an explicit full commit. Affinity's selected maintained branch has no versioned release; its resolved revision and the included overlay identify that build. CPU code is portable rather than compiled for the build runner's native ISA.

CI runs the real executable's help command, checks its installed source identity, uploads provenance, and publishes an immutable candidate tag. Candidate publication does not change a rolling channel. GPU inference, the selected model and decoding modes, ordinary installation and clean shutdown must pass on the target hardware before promotion. The workflow does not download model weights or claim GPU support from a CPU build.

## Strata entrypoints

`strata-prepare` accepts `--model`, `--auxiliary`, `--output`, `--main-revision` and `--aux-revision`. It uses upstream `tools/dsv41/pack_gguf.py`, installs the 2.00 bpw expert profile and checks the generated pack with `strata-dsv41 --pack-info`. Give the original GGUF directories read-only mounts and a separate writable output directory. It refuses to overwrite an existing pack and records source/model identities and generated file sizes.

`strata-serve --pack PACK --context 8192 --decoding baseline --host 0.0.0.0 --port 18920` starts upstream `serve/server.py` with the four-GPU DeepSeek V4.1 configuration. Select `--decoding dspark` for its matched drafter. The profile uses one sequence, all four GPU IDs, native `--tp 1`, six routed experts and automatic expert mmap. The pack's expert profile is copied to temporary runtime storage so a read-only pack remains usable.

The HTTP server exposes chat APIs. Native full-prompt timings and standard cached-history raw-Completions timings are separate measurements; API availability alone does not establish benchmark compatibility.

## Channel promotion

After reviewing actual-image GPU qualification, run **Promote qualified R9700 engine** with its exact manifest digest, full source revision and a link to the public qualification review. The workflow checks the registry config's architecture and source identity, copies that same manifest to a unique release tag and the engine's rolling `ENGINE-rocm-10.1` channel, then verifies both digests. It does not rebuild or select a different candidate. Record the previous channel digest before promotion for rollback.
