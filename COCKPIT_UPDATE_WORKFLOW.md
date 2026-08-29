# Cockpit Toolbox Update Workflow

Use this checklist whenever a toolbox in this repository is added, renamed,
updated, or retired.

## Cockpit location

- Repository: `/home/kyuz0/Documents/Projects/ai-toolbox-cockpit`
- Catalogue: `ai_toolbox_cockpit/assets/toolboxes.json`
- Read the cockpit repository's `AGENTS.md` before editing it.

## Source inventory

Determine the active toolbox set from all three current surfaces:

- `toolboxes/Dockerfile.*`
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
Remove retired records and their platform references together. For this
migration, replace `r9700-llama-rocm-7-14` with
`r9700-llama-rocm-10-0`, add `r9700-llama-vulkan-rocmfpx`, and change the
R9700 llama.cpp default to the ROCm 10.0 ID.

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
python -m pytest -q tests/test_catalog.py tests/test_app.py
git diff --check
```

Do not start containers, GPU servers, downloads, or toolbox sessions during
local catalogue validation. Review both repository diffs before committing or
pushing changes.
