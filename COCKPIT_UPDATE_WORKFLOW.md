# Cockpit Toolbox Update Workflow

Use this checklist whenever a toolbox in this repository is added, renamed,
updated, or retired.

## Cockpit location

- Repository: `/home/kyuz0/Documents/Projects/ai-toolbox-cockpit`
- Catalogue: `ai_toolbox_cockpit/assets/toolboxes.json`
- Read the cockpit repository's `AGENTS.md` before editing it.

## Source inventory

Determine the active toolbox set from all three current surfaces:

- `toolboxes/Dockerfile.*` and `toolboxes/*/Dockerfile`
- `README.md`
- `refresh-toolboxes.sh`

Do not treat benchmark results or `.github/workflows/prune-old-toolboxes.yml`
as active catalogue entries. They may intentionally retain historical names.

The cockpit is curated. Do not automatically expose every future experimental
Dockerfile without checking the repository's README and refresh script.

## Update the cockpit

For each exposed toolbox, keep these three surfaces synchronized in
`toolboxes.json`:

1. The toolbox record: `id`, `name`, `container_name`, full OCI `image`, channel,
   maturity, description, runtime profile, capabilities, and feature states.
2. The `r9700` platform's `toolbox_ids` list.
3. The `r9700.defaults` entry when the default toolbox changes.

Use IDs such as `r9700-llama-rocm-10-0` for image tags such as `rocm-10.0`.
Remove retired records and their platform references together.

## New engine integrations

Do not force a model-specific runtime into an existing backend. When a toolbox
introduces a distinct inference engine or owns an immutable model layout, add a
first-class Cockpit backend under
`ai_toolbox_cockpit/backends/<backend_id>/`. Register it explicitly and update:

1. `ai_toolbox_cockpit/backends/registry.py`
2. `BACKEND_IDS` and `MODEL_KINDS` in `catalog/schema.py`
3. The backend entry and model metadata in `assets/models.json`
4. The toolbox record, platform assignment, and backend default in
   `assets/toolboxes.json`
5. Backend command, catalogue, and UI-mount tests

Keep host-side download, verification, preparation, and launch logic in the
Cockpit backend. The toolbox image may include compiled runtime dependencies
and an upstream utility needed by that logic, but do not add repository-root
wrapper scripts for model operations.

The R9V integration is the reference example: backend `r9v`, toolbox
`r9700-r9v-qwen38-rocm-10-0`, assigned only to platform `r9700`. Its Cockpit
backend owns the license-confirmed pinned Qwen3.8 package download, artifact and
PLE verification, upstream PLE extraction, and fixed dual-R9700 launch profile.
The toolbox repository owns only the ROCm 10.0 runtime image and documentation.

Search the entire cockpit for every renamed or removed ID:

```sh
rg -n '<old-toolbox-id>|<old-image-tag>' \
  /home/kyuz0/Documents/Projects/ai-toolbox-cockpit
```

Update active tests and model configuration references. Preserve historical
fixtures unless they expose a retired toolbox to users. Do not transfer
calibrations to a different toolbox identity without an explicit decision.

## Validate

Run from the cockpit repository:

```sh
python -m json.tool ai_toolbox_cockpit/assets/toolboxes.json >/dev/null
python -m json.tool ai_toolbox_cockpit/assets/models.json >/dev/null
python -m pytest -q tests/test_catalog.py tests/test_app.py tests/test_r9v_commands.py
git diff --check
```

Do not start containers, GPU servers, downloads, or toolbox sessions during
local catalogue validation. For a new engine, separately exercise its pure
command builder and then run image/runtime GPU smoke tests on the target host.
Model downloads still require explicit acceptance of their license in Cockpit.
Review both repository diffs before committing or pushing changes.
