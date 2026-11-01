#!/usr/bin/env python3
"""Create DeepSeek V4.1 pack metadata, retaining original read-only GGUF weights."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--auxiliary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--main-revision', required=True)
    parser.add_argument('--aux-revision', required=True)
    args = parser.parse_args()
    if any(not re.fullmatch(r'[0-9a-f]{40}', revision) for revision in [args.main_revision, args.aux_revision]):
        parser.error('Model revisions must be immutable forty-character commits.')
    output = args.output.resolve()
    if output.exists():
        parser.error('The native pack already exists. Select its validated preparation or a new output directory.')
    shards = [f'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-{i:05d}-of-00004.gguf' for i in range(1, 5)]
    engram = args.model / 'DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf'
    metadata = args.auxiliary / 'UD-Q8_K_XL/DeepSeek-V4.1-Flash-1017-UD-Q8_K_XL-00001-of-00009.gguf'
    draft = args.auxiliary / 'dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf'
    for path in [*(args.model / name for name in shards), engram, metadata, draft]:
        if not path.is_file():
            parser.error('Missing required model artifact: ' + str(path))
    output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve a failed preparation for inspection; never erase an existing pack.
    work = Path(tempfile.mkdtemp(prefix='.' + output.name + '-preparing-', dir=output.parent))
    command = [sys.executable, '/opt/strata/tools/dsv41/pack_gguf.py', '--model', str(args.model),
               '--out', str(work), '--engram', str(engram), '--engram-meta', str(metadata),
               '--dspark-gguf', str(draft), '--shards', *shards]
    subprocess.run(command, check=True)
    shutil.copyfile('/opt/strata/data/dsv41/profile-2.00.bin', work / 'expert-profile.bin')
    subprocess.run(['strata-dsv41', '--pack', str(work), '--pack-info'], check=True)
    receipt = {'main_revision': args.main_revision, 'aux_revision': args.aux_revision,
               'source_revision': Path('/opt/strata/share/toolbox/source-revision').read_text().strip(),
               'files': {str(p.relative_to(work)): p.stat().st_size for p in work.rglob('*') if p.is_file()}}
    (work / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    work.rename(output)
    print('Prepared metadata-only native pack:', output, flush=True)


if __name__ == '__main__':
    main()
