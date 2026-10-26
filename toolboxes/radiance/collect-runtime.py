"""Copy only ROCm runtime dependencies; use the distro's libc and compiler runtime."""
from pathlib import Path
import shutil, subprocess, re
root = Path('/opt/radiance')
libs = root / 'lib/runtime'
libs.mkdir(parents=True, exist_ok=True)
comgr = Path('/opt/rocm/lib/libamd_comgr.so.3')
assert comgr.exists(), 'ROCm comgr runtime is required'
copied = {str(comgr)}
elfs = []
for path in root.rglob('*'):
    if path.is_file():
        with path.open('rb') as f:
            if f.read(4) == b'\x7fELF': elfs.append(path)
for path in elfs + [comgr]:
    result = subprocess.run(['ldd', str(path)], text=True, capture_output=True)
    if 'not found' in result.stdout: raise RuntimeError(result.stdout)
    for name in re.findall(r'=> (/opt/rocm/\S+)', result.stdout):
        source = Path(name)
        copied.add(str(source))
        shutil.copy2(source.resolve(), libs / source.name)
shutil.copy2(comgr.resolve(), libs / comgr.name)

(root / 'share/doc/radiance/copied-runtime-paths.txt').write_text('\n'.join(sorted(copied))+'\n')
