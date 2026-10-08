#!/usr/bin/env python3
"""Generate a local guarded installer from reviewed upstream bytes; never replace the original."""
import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = '9ca4db6de1954b0871a1678ab08f636035ca35c04db07f3ad3aef4fbf429d61b'
OLD = b'    open(p, "w").write("\\n".join(lines))'
NEW = b'    assert open(p).read() == "\\n".join(lines), f"SwiftBuild compatibility patch required: {p}"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.repo.expanduser().resolve(strict=True) / 'install-toolchain.sh'
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_SHA256 or original.count(OLD) != 1:
        raise ValueError('Upstream installer differs from the reviewed LF fixed commit')
    updated = original.replace(OLD, NEW, 1)
    output = (args.output or source.with_name('install-toolchain-wsl-guarded.sh')).expanduser().absolute()
    if output == source or output.is_symlink():
        raise ValueError('Output must be a separate non-symlink file')
    if output.exists():
        if output.read_bytes() != updated:
            raise ValueError('Output exists with different content; refusing overwrite')
    else:
        with output.open('xb') as stream:
            stream.write(updated)
    print('Generated: ' + str(output))
    print('SHA256: ' + hashlib.sha256(updated).hexdigest())
    print('One statement changed; original upstream installer preserved. Review before executing.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit('ERROR: ' + str(error))
