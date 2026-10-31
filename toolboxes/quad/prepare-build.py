"""Resolve stable sources and prepare reviewed engine-specific build contexts."""
import argparse, json, os, re, shutil, subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('engine', choices=['affinity', 'hipfire', 'strata'])
p.add_argument('--revision', default='latest')
p.add_argument('--destination', required=True, type=Path)
a = p.parse_args()
repo, fallback = {'affinity': ('neuromaniacMD/affinity', 'v4-fixes'), 'hipfire': ('warpfront/hipfire', None), 'strata': ('Niko1221/Strata', None)}[a.engine]
url = 'https://github.com/' + repo + '.git'
root = a.destination.resolve()
root.mkdir(parents=True, exist_ok=False)
selector = a.revision
version = 'source'
if selector == 'latest':
    if fallback:
        selector, version = 'refs/heads/' + fallback, fallback
    else:
        tags = subprocess.check_output(['git', 'ls-remote', '--tags', '--refs', url], text=True)
        releases = []
        for line in tags.splitlines():
            ref = line.split()[1]
            match = re.fullmatch(r'refs/tags/v?(\d+)\.(\d+)\.(\d+)', ref)
            if match: releases.append((tuple(map(int, match.groups())), ref))
        if not releases: raise RuntimeError('No stable upstream release found')
        selector = max(releases)[1]
        version = selector.removeprefix('refs/tags/')
elif not re.fullmatch('[0-9a-f]{40}', selector):
    raise ValueError('Revision must be latest or a complete commit SHA')
source = root / 'source'
subprocess.run(['git', 'init', str(source)], check=True)
subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', url, selector], check=True)
subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if a.revision != 'latest' and revision != a.revision: raise RuntimeError('Source pin mismatch')
subprocess.run(['git', '-C', str(source), 'submodule', 'update', '--init', '--recursive', '--depth', '1'], check=True)
recipes = Path(__file__).resolve().parent
if a.engine == 'hipfire':
    context = source
    dockerfile = source / 'Dockerfile.toolbox'
    dockerfile.write_text((source / 'Containerfile').read_text() + (recipes / 'hipfire-toolbox-stage.Containerfile').read_text())
else:
    context = root
    dockerfile = recipes / ('Dockerfile.' + a.engine + '-rocm-10.1')
    if a.engine == 'affinity': shutil.copyfile(recipes / 'raw-http-v2.patch', root / 'raw-http-v2.patch')
record = dict(engine=a.engine, repository=url, selector=selector, source_revision=revision, version=version, channel=a.engine + '-rocm-10.1', context=str(context), dockerfile=str(dockerfile))
(root / 'source-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
if os.environ.get('GITHUB_OUTPUT'):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key, value in record.items(): output.write(f'{key}={value}\n')
print(json.dumps(record, indent=2))
