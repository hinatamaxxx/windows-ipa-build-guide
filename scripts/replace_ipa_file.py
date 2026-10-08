#!/usr/bin/env python3
"""Write a new IPA with one entry replaced, keeping every other entry as is.

The replacement keeps the original entry's Unix mode (e.g. 0755 for a dylib),
and entries whose mode a Windows zip writer dropped get 0755 (Mach-O) or 0644. Refuses to overwrite an existing output and
never modifies the base IPA. Works with Windows or WSL Python.

It only swaps an existing file. Adding a load command for a new dylib is a
different operation (insert_dylib / Theos jailed packaging) and is refused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MACHO = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}


def unix_info(src: zipfile.ZipFile, info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """Restore Unix modes that a Windows zip writer (e.g. .NET ZipArchive) dropped.

    Without them the app and extension executables lose their execute bit.
    """
    fixed = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    fixed.compress_type = info.compress_type
    fixed.create_system = 3
    if info.is_dir():
        mode = 0o40755
    else:
        with src.open(info) as f:
            mode = 0o100755 if f.read(4) in MACHO else 0o100644
    fixed.external_attr = (mode << 16) | (0x10 if info.is_dir() else 0)
    fixed.file_size = info.file_size
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ipa", type=Path, required=True, help="base IPA (read only)")
    ap.add_argument("--entry", required=True, help="e.g. Payload/App.app/Frameworks/Tweak.dylib")
    ap.add_argument("--file", type=Path, required=True, help="replacement file")
    ap.add_argument("--output", type=Path, required=True, help="new IPA path (must not exist)")
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    data = args.file.read_bytes()
    tmp = args.output.with_name(args.output.name + ".partial")
    normalized = 0
    with zipfile.ZipFile(args.ipa) as src:
        names = src.namelist()
        if args.entry not in names:
            raise SystemExit(f"{args.entry} not in base IPA; this tool only replaces existing entries")
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as dst:
            for info in src.infolist():
                if info.filename == args.entry:
                    new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    new.create_system = 3  # Unix, so external_attr carries the mode
                    new.external_attr = info.external_attr if info.create_system == 3 else (0o100755 << 16)
                    new.compress_type = zipfile.ZIP_DEFLATED
                    dst.writestr(new, data)
                else:
                    out = info
                    if info.create_system != 3:
                        out = unix_info(src, info)
                        normalized += 1
                    with src.open(info) as fsrc, dst.open(out, "w", force_zip64=info.file_size > 0x7FFFFFFF) as fdst:
                        shutil.copyfileobj(fsrc, fdst, 1 << 20)
    with zipfile.ZipFile(tmp) as check:
        bad = check.testzip()
        if bad:
            raise SystemExit(f"CRC check failed for {bad}")
        info = check.getinfo(args.entry)
        inside = hashlib.sha256(check.read(args.entry)).hexdigest()
        count = len(check.namelist())
    # Sync clients (iCloud Drive, OneDrive) briefly lock a freshly written file.
    for attempt in range(30):
        try:
            tmp.rename(args.output)
            break
        except PermissionError:
            if attempt == 29:
                raise SystemExit(f"could not rename {tmp} (locked by another process); the verified file is kept there")
            time.sleep(1)
    report = {
        "output": str(args.output),
        "outputSha256": sha256(args.output),
        "entry": args.entry,
        "entrySha256": inside,
        "fileSha256": hashlib.sha256(data).hexdigest(),
        "entryMode": oct((info.external_attr >> 16) & 0o7777),
        "entries": count,
        "baseEntries": len(names),
        "modesRestored": normalized,
        "executables": sum(1 for i in zipfile.ZipFile(args.output).infolist() if (i.external_attr >> 16) & 0o100 and not i.is_dir()),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["entrySha256"] == report["fileSha256"] and count == len(names) else 1


if __name__ == "__main__":
    sys.exit(main())
