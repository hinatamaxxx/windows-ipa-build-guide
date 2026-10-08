#!/usr/bin/env python3
"""Reuse an approved Linux xtool environment; build and verify unsigned IPA bytes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

COMMIT = 'acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942'
SHIP_HASH = 'a79d42afc6d253f968d0e7a43b41c7d577d0db1766d8cdd9b79ddae2a1ee10ef'
# ship.sh --device imports placeholder_hits from tools/asc.py; review it together with ship.sh.
ASC_HASH = '6d5fa9d3ebf44c3fb7c43971e9d0e10035c5bed9a4b38ce2047d7316e3d3d81e'
SPEC_HASHES = {
    'SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec':
        'ff64429a04f70c1cc2d91679eec7672d1eb62aaa14733e5bcd7940b9159f0faa',
    'SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec':
        'b48881a3b85b2d52e062e72eca632c27c32013c099ef64844443865283e5a9cf',
    'SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec':
        '14a20b902c664af02b487b9f6423a00dda33fd959aeffe1a659e02287dc9da01',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def version(value):
    return f'{value >> 16}.{(value >> 8) & 255}.{value & 255}'


def macho(binary):
    require(len(binary) >= 32, 'Truncated Mach-O header')
    magic, cpu, subtype, kind, count, total, flags, reserved = struct.unpack_from('<8I', binary)
    require(magic == 0xFEEDFACF and cpu == 0x0100000C and kind == 2,
            'Expected a thin arm64 executable Mach-O')
    end, offset = 32 + total, 32
    require(end <= len(binary) and count <= total // 8, 'Invalid load-command bounds')
    platform = minimum = sdk = None
    for _ in range(count):
        require(offset + 8 <= end, 'Truncated load command')
        command, size = struct.unpack_from('<2I', binary, offset)
        require(size >= 8 and size % 8 == 0 and offset + size <= end,
                'Invalid load-command size')
        require(command != 0x1D, 'Code signature present: this helper requires an unsigned app')
        if command == 0x32:
            require(size >= 24, 'Truncated LC_BUILD_VERSION')
            platform, min_value, sdk_value, tools = struct.unpack_from('<4I', binary, offset + 8)
            require(size >= 24 + tools * 8, 'Truncated build tools')
            minimum, sdk = version(min_value), version(sdk_value)
        elif command == 0x25:
            require(size >= 16, 'Truncated LC_VERSION_MIN_IPHONEOS')
            min_value, sdk_value = struct.unpack_from('<2I', binary, offset + 8)
            platform, minimum, sdk = 2, version(min_value), version(sdk_value)
        offset += size
    require(offset == end and platform == 2, 'Expected complete iOS load commands')
    return {'architecture': 'arm64', 'platform': 'iOS', 'minimum_os': minimum,
            'macho_sdk_version': sdk, 'macho_code_signature_present': False}


def inspect_app(app, expected_id=None):
    require(app.is_dir() and not app.is_symlink() and app.name.endswith('.app'), 'Invalid app directory')
    app = app.resolve()
    paths = sorted(app.rglob('*'))
    for path in paths:
        require(path.name not in ('embedded.mobileprovision', '_CodeSignature'),
                f'Signing/provisioning artifact present: {path.relative_to(app)}')
        require(path.resolve().is_relative_to(app), f'Path escapes app: {path.relative_to(app)}')
        require(path.is_symlink() or path.is_file() or path.is_dir(), 'Unsupported special file')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    bundle_id, executable = info.get('CFBundleIdentifier'), info.get('CFBundleExecutable')
    require(isinstance(bundle_id, str) and bundle_id, 'Missing bundle identifier')
    require(isinstance(executable, str) and executable and Path(executable).name == executable,
            'Invalid executable name')
    require(expected_id is None or bundle_id == expected_id, 'Bundle identifier mismatch')
    binary = (app / executable).read_bytes()
    report = macho(binary)
    extensions = []
    for extension in sorted(app.rglob('*.appex')):
        extension_info = plistlib.loads((extension / 'Info.plist').read_bytes())
        name = extension_info.get('CFBundleExecutable')
        require(isinstance(name, str) and name and Path(name).name == name, 'Invalid extension executable')
        extensions.append({'path': extension.relative_to(app).as_posix(),
                           **macho((extension / name).read_bytes())})
    report.update(bundle_id=bundle_id, executable=executable,
                  bundle_version=info.get('CFBundleVersion'),
                  short_version=info.get('CFBundleShortVersionString'),
                  executable_sha256=hashlib.sha256(binary).hexdigest(),
                  apple_provisioning_profile_present=False,
                  apple_distribution_signing_performed=False, extensions=extensions)
    return app, info, paths, report


def package_app(app, destination, expected_id=None):
    app, info, paths, report = inspect_app(app, expected_id)
    with destination.open('xb') as output:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in paths:
                name = 'Payload/' + app.name + '/' + path.relative_to(app).as_posix()
                if path.is_symlink():
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(entry, os.readlink(path))
                elif path.is_file():
                    archive.write(path, name)
                else:
                    archive.write(path, name + '/')
    with zipfile.ZipFile(destination) as archive:
        require(archive.testzip() is None, 'ZIP CRC check failed')
        names = archive.namelist()
        prefix = 'Payload/' + app.name + '/'
        require(len(names) == len(set(names)) and all(n.startswith(prefix) for n in names),
                'Invalid Payload layout or duplicate entries')
        require(prefix + info['CFBundleExecutable'] in names, 'Missing packaged executable')
        require(plistlib.loads(archive.read(prefix + 'Info.plist')) == info, 'Packaged Info.plist mismatch')
        require(hashlib.sha256(archive.read(prefix + info['CFBundleExecutable'])).hexdigest()
                == report['executable_sha256'], 'Packaged executable mismatch')
    report.update(zip_crc_check='passed', payload_app_count=1,
                  ipa_bytes=destination.stat().st_size, ipa_sha256=sha256(destination))
    return report


def environment(args):
    require(sys.platform == 'linux' and os.geteuid() != 0, 'Run in WSL/Linux as the normal non-root user')
    project = args.project.expanduser().resolve(strict=True)
    require((project / 'Package.swift').is_file() and (project / 'xtool.yml').is_file(),
            'Project must already contain Package.swift and xtool.yml')
    repo = (args.repo or Path.home() / 'omarchy-apple-dev-acd373c').expanduser().resolve(strict=True)
    ship = repo / 'ship.sh'
    require(sha256(ship) == SHIP_HASH, 'ship.sh differs from the reviewed fixed commit; review before execution')
    require(sha256(repo / 'tools/asc.py') == ASC_HASH,
            'tools/asc.py differs from the reviewed fixed commit; review before execution')
    swift_bin = (args.swift_bin or Path('/usr/lib/swift/usr/bin')).expanduser().resolve(strict=True)
    swift = swift_bin / 'swift'
    require(swift.is_file() and os.access(swift, os.X_OK), 'Missing executable Swift')
    env = dict(os.environ)
    for key in ('ASC_KEY_ID', 'ASC_KEY_PATH', 'ASC_ISSUER_ID'):
        env.pop(key, None)
    env['PATH'] = str(swift_bin) + ':' + str(Path.home() / '.local/bin') + ':' + env.get('PATH', '')
    require(shutil.which('xtool', path=env['PATH']) is not None, 'xtool is not installed')
    python = Path.home() / 'pymobile3-venv/bin/python'
    require(python.is_file(), 'Missing ship.sh resource-processing Python')
    # An Arch python minor upgrade leaves the venv unusable; ship.sh needs plistlib and asc.py's cryptography.
    venv = subprocess.run([str(python), '-c', 'import plistlib, cryptography'], env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    require(venv.returncode == 0, 'pymobile3-venv cannot import cryptography; recreate it (docs/setup.md)')
    swift_version = subprocess.check_output([str(swift), '--version'], env=env, text=True).strip()
    require('Swift version 6.4 ' in swift_version, 'Swift version changed; review compatibility before building')
    sdk_list = subprocess.check_output([str(swift), 'sdk', 'list'], env=env, text=True).splitlines()
    require('darwin' in sdk_list, 'darwin Swift SDK is not registered')
    sdk = (args.sdk or Path.home() / '.swiftpm/swift-sdks/darwin.artifactbundle').expanduser().resolve(strict=True)
    developer = sdk / 'Developer'
    ios = developer / 'Platforms/iPhoneOS.platform/Developer'
    settings = json.loads((ios / 'SDKs/iPhoneOS.sdk/SDKSettings.json').read_text())
    require(sdk == (Path.home() / '.swiftpm/swift-sdks/darwin.artifactbundle').resolve(),
            'SDK must be the registered darwin bundle used by this fixed ship.sh')
    env['ACTOOL'] = str(ios / 'usr/bin/actool')
    for path in (ios / 'usr/bin/actool', sdk / 'OpenAppleMacrosServer'):
        require(path.is_file() and os.access(path, os.X_OK), f'Missing executable SDK tool: {path}')
    specs = swift_bin.parent / 'share/pm'
    for relative, expected in SPEC_HASHES.items():
        require(sha256(specs / relative) == expected,
                f'SwiftBuild compatibility file changed: {relative}; consult docs/setup.md')
    metadata = {'project': str(project), 'repo': str(repo), 'reviewed_source_commit': COMMIT,
                'ship_sha256': SHIP_HASH, 'asc_sha256': ASC_HASH, 'swift_version': swift_version,
                'registered_sdks': sdk_list, 'source_sdk_version': settings['Version'],
                'sdk_path': str(sdk), 'swiftbuild_spec_hashes': SPEC_HASHES}
    return project, ship, env, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--swift-bin', type=Path)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--bundle-id')
    parser.add_argument('--app-name', help='Expected leaf name such as HelloOmarchy.app')
    parser.add_argument('--check', action='store_true', help='Read-only environment check; no build or output files')
    args = parser.parse_args()
    project, ship, env, metadata = environment(args)
    if args.check:
        print(json.dumps({'environment_check': 'passed', **metadata}, indent=2))
        return
    require(args.output_dir is not None, 'Building requires --output-dir')
    if args.app_name:
        require(Path(args.app_name).name == args.app_name and args.app_name.endswith('.app'), 'Invalid --app-name')
    # ship.sh processes only the first xtool/*.app it finds, so a stale second app could be packaged unprocessed.
    stale = sorted(p.name for p in (project / 'xtool').glob('*.app') if p.is_dir())
    require(len(stale) <= 1, f'Several apps under xtool/: {stale}; move the stale ones out of xtool/ first')
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S-%f_UTC__')
    run = Path(tempfile.mkdtemp(prefix=stamp, dir=output))
    log = run / 'build.log'
    with log.open('x') as stream:
        completed = subprocess.run(['bash', str(ship), '--device'], cwd=project, env=env,
                                   stdout=stream, stderr=subprocess.STDOUT)
    require(completed.returncode == 0, f'Build failed ({completed.returncode}); inspect {log}. No installer was run.')
    apps = sorted(p for p in (project / 'xtool').glob('*.app') if p.is_dir())
    require(len(apps) == 1, f'Expected one app under xtool/, found {len(apps)}')
    app = apps[0]
    require(args.app_name is None or app.name == args.app_name, f'Built app is {app.name}, not {args.app_name}')
    ipa = run / (app.stem + '-unsigned.ipa')
    try:
        report = package_app(app, ipa, args.bundle_id)
    except Exception:
        if ipa.exists():
            ipa.unlink()  # Only this newly created private run's incomplete output.
        raise
    report.update(metadata, ipa=str(ipa), build_log=str(log),
                  verification_scope='Payload/CRC, main and extension arm64 iOS executables; no device/signing validation')
    report_path = run / 'verification.json'
    with report_path.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'verification_report': str(report_path), **report}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, plistlib.InvalidFileException,
            zipfile.BadZipFile, KeyError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
