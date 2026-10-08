#!/usr/bin/env python3
"""Check/apply three exact Swift 6.4 xcspec compatibility changes, preserving originals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

SPECS = (
    ('SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec',
     'STRINGS_FILE_INPUT_ENCODING', '$(InputFileTextEncoding)', 'utf-8', 1,
     '2d50c20db8a9239d7801db38b5e937a90eb747a9b9f73f557671d8d8a9543cdb',
     'ff64429a04f70c1cc2d91679eec7672d1eb62aaa14733e5bcd7940b9159f0faa'),
    ('SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec',
     'STRINGS_FILE_OUTPUT_ENCODING', 'UTF-16', 'binary', 2,
     '5bf5f1ad80df1241cd6643b1c5dc12b80d48ddf2106ee97b82de9cb4ed455bd6',
     'b48881a3b85b2d52e062e72eca632c27c32013c099ef64844443865283e5a9cf'),
    ('SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec',
     'STRINGS_FILE_OUTPUT_ENCODING', 'UTF-16', 'binary', 1,
     '1e6632599489aa287d3418818c4268f6c389044f186e754c058a87ecbe04fcf1',
     '14a20b902c664af02b487b9f6423a00dda33fd959aeffe1a659e02287dc9da01'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def changed(data, setting, old, new, count):
    lines = data.decode().split('\n')
    hits = []
    for i, line in enumerate(lines):
        if f'Name = "{setting}";' in line or f'Name = {setting};' in line:
            for j in range(i + 1, min(i + 12, len(lines))):
                if 'DefaultValue =' in lines[j]:
                    hits.append(j)
                    break
    if len(hits) != count:
        raise ValueError('Unexpected setting count: ' + setting)
    for j in hits:
        if lines[j].count(f'"{old}";') != 1:
            raise ValueError('Unexpected original value: ' + setting)
        lines[j] = lines[j].replace(f'"{old}";', f'"{new}";')
    return '\n'.join(lines).encode()


def plan(root):
    result = []
    if root.absolute() != root.resolve():
        raise ValueError('Root must not traverse a symlink or noncanonical path')
    for relative, setting, old, new, count, before, after in SPECS:
        path = root / relative
        if path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError('Unexpected file: ' + str(path))
        original = path.read_bytes()
        current = digest(original)
        if current == after:
            result.append((path, original, original, False))
            continue
        if current != before:
            raise ValueError('Unknown source hash: ' + str(path))
        updated = changed(original, setting, old, new, count)
        if digest(updated) != after:
            raise ValueError('Unexpected patched hash: ' + str(path))
        result.append((path, original, updated, True))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--root', type=Path, default=Path('/usr/lib/swift/usr/share/pm'))
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    plans = plan(args.root.expanduser().absolute())
    print(json.dumps([{'path': str(p), 'change_needed': change,
                       'original_sha256': digest(old), 'result_sha256': digest(new)}
                      for p, old, new, change in plans], indent=2))
    changes = [(p, old, new) for p, old, new, change in plans if change]
    if args.check or not changes:
        return
    if os.geteuid() != 0 or args.backup is None:
        raise ValueError('--apply requires root and --backup pointing to a new directory')
    backup = args.backup.expanduser().absolute()
    if backup != backup.resolve() or backup.exists():
        raise ValueError('Backup must be a new canonical directory')
    for path, old, new in changes:
        st = path.stat()
        if st.st_uid != 0 or st.st_mode & 0o777 != 0o644:
            raise ValueError('Expected root-owned mode 0644: ' + str(path))
    backup.mkdir(mode=0o755, parents=True, exist_ok=False)
    for path, old, new in changes:
        saved = backup / path.name
        shutil.copy2(path, saved)
        if saved.read_bytes() != old:
            raise ValueError('Backup verification failed')
    for path, old, new in changes:
        if path.read_bytes() != old:
            raise ValueError('Source changed during patch')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ipa-spec-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(new)
            os.chmod(temporary, 0o644)
            os.chown(temporary, 0, 0)
            os.replace(temporary, path)
            temporary = None
            if digest(path.read_bytes()) != digest(new):
                raise ValueError('Post-write verification failed')
        finally:
            if temporary is not None:
                temporary.unlink()
    print('Originals preserved in ' + str(backup))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit('ERROR: ' + str(error))
