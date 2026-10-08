#!/usr/bin/env python3
"""Build an arm64 iOS Objective-C/C dynamic library in WSL without Theos or a Mac.

Optionally builds a Go package as a c-archive first and links it in. Uses the
existing Swift clang, the darwin Swift SDK's iPhoneOS SDK, ld64.lld and the
Xcode toolchain's libclang_rt.ios.a. Writes the dylib, a JSON report and logs
to a new timestamped directory; never overwrites earlier output.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
BUNDLE = HOME / ".swiftpm/swift-sdks/darwin.artifactbundle"
CLANG = Path("/usr/lib/swift/usr/bin/clang")
OBJDUMP = Path("/usr/lib/swift/usr/bin/llvm-objdump")


def sdk_path(version: str | None) -> Path:
    sdks = BUNDLE / "Developer/Platforms/iPhoneOS.platform/Developer/SDKs"
    if version:
        return sdks / f"iPhoneOS{version}.sdk"
    found = sorted(p for p in sdks.glob("iPhoneOS*.*.sdk") if p.is_dir())
    if not found:
        raise SystemExit(f"no iPhoneOS SDK under {sdks}")
    return found[-1]


def builtins() -> Path:
    found = sorted((BUNDLE / "Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang").glob("*/lib/darwin/libclang_rt.ios.a"))
    if not found:
        raise SystemExit("libclang_rt.ios.a not found in the Xcode toolchain of the SDK bundle")
    return found[-1]


def run(cmd: list[str], log, cwd: Path | None = None, env: dict | None = None) -> None:
    log.write("$ " + shlex.join(cmd) + "\n")
    log.flush()
    proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
    if proc.returncode:
        raise SystemExit(f"command failed ({proc.returncode}); see {log.name}")


def check() -> int:
    items = {
        "clang": CLANG,
        "llvm-objdump": OBJDUMP,
        "ld64.lld": BUNDLE / "toolset/bin/ld64.lld",
        "iPhoneOS SDK": sdk_path(None),
        "libclang_rt.ios.a": builtins(),
    }
    ok = True
    for name, path in items.items():
        exists = path.exists()
        ok &= exists
        print(f"{'ok ' if exists else 'MISSING'} {name}: {path}")
    go = subprocess.run(["go", "version"], capture_output=True, text=True)
    print(("ok  " if go.returncode == 0 else "MISSING ") + "go: " + (go.stdout.strip() or go.stderr.strip()))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only verify the toolchain")
    ap.add_argument("--project", type=Path, help="working directory for relative paths")
    ap.add_argument("--source", action="append", default=[], help="source file (repeatable)")
    ap.add_argument("--sources-file", type=Path, help="file listing sources, one per line")
    ap.add_argument("--cflag", action="append", default=[], help="extra compiler flag (repeatable)")
    ap.add_argument("--framework", action="append", default=[])
    ap.add_argument("--lib", action="append", default=[], help="system library name, e.g. resolv")
    ap.add_argument("--archive", action="append", default=[], help="extra static archive to link")
    ap.add_argument("--go-package", help="Go package to build as c-archive first, e.g. ./cmd/bridge")
    ap.add_argument("--go-dir", type=Path, help="module directory for --go-package (default: project)")
    ap.add_argument("--go-tags", default="")
    ap.add_argument("--go-out", type=Path, help="c-archive path (its header is written beside it)")
    ap.add_argument("--min-ios", default="15.0")
    ap.add_argument("--sdk-version", help="e.g. 27.0 (default: newest in the bundle)")
    ap.add_argument("--install-name", required=False)
    ap.add_argument("--name", default="Library", help="output file stem")
    ap.add_argument("--output-dir", type=Path, help="parent of the timestamped output directory")
    args = ap.parse_args()
    if args.check:
        return check()
    if not args.project or not args.install_name or not args.output_dir:
        ap.error("--project, --install-name and --output-dir are required")

    project = args.project.resolve()
    sources = list(args.source)
    if args.sources_file:
        sources += [l.strip() for l in (project / args.sources_file).read_text().splitlines() if l.strip() and not l.startswith("#")]
    if not sources:
        ap.error("no sources")
    out = args.output_dir.resolve() / f"{args.name}-{dt.datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=False)
    sdk = sdk_path(args.sdk_version)
    ld = BUNDLE / "toolset/bin/ld64.lld"
    target = ["-target", f"arm64-apple-ios{args.min_ios}", "-isysroot", str(sdk)]
    log = open(out / "build.log", "w")

    if args.go_package:
        go_out = (project / args.go_out) if args.go_out else project / ".build/libgo.a"
        go_out.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CGO_ENABLED="1", GOOS="ios", GOARCH="arm64",
                   CC=shlex.join([str(CLANG), *target]),
                   CGO_CFLAGS=shlex.join(target),
                   CGO_LDFLAGS=shlex.join([*target, f"-fuse-ld={ld}"]))
        cmd = ["go", "build", "-buildmode=c-archive", "-trimpath", "-o", str(go_out)]
        if args.go_tags:
            cmd += ["-tags", args.go_tags]
        run(cmd + [args.go_package], log, cwd=(project / args.go_dir) if args.go_dir else project, env=env)
        args.archive.insert(0, str(go_out))

    dylib = out / f"{args.name}.dylib"
    # -mlinker-version makes clang pass -arch/-platform_version to ld64.lld;
    # libclang_rt.ios.a provides __isPlatformVersionAtLeast for @available.
    cmd = [str(CLANG), *target, "-mlinker-version=907", "-dynamiclib", *args.cflag, *sources]
    for f in args.framework:
        cmd += ["-framework", f]
    cmd += [f"-l{l}" for l in args.lib]
    cmd += [str(project / a) if not os.path.isabs(a) else a for a in args.archive]
    cmd += [str(builtins()), "-install_name", args.install_name, f"-fuse-ld={ld}", "-Wl,-adhoc_codesign", "-o", str(dylib)]
    run(cmd, log, cwd=project)

    headers = subprocess.run([str(OBJDUMP), "--macho", "--private-headers", str(dylib)], capture_output=True, text=True).stdout
    used = subprocess.run([str(OBJDUMP), "--macho", "--dylibs-used", str(dylib)], capture_output=True, text=True).stdout
    def field(block: str, key: str) -> str | None:
        part = headers.split(block, 1)
        if len(part) < 2:
            return None
        for line in part[1].splitlines()[:8]:
            bits = line.split()
            if len(bits) >= 2 and bits[0] == key:
                return bits[1]
        return None
    report = {
        "dylib": str(dylib),
        "sha256": hashlib.sha256(dylib.read_bytes()).hexdigest(),
        "bytes": dylib.stat().st_size,
        "installName": args.install_name,
        "platform": field("LC_BUILD_VERSION", "platform"),
        "minos": field("LC_BUILD_VERSION", "minos"),
        "sdk": field("LC_BUILD_VERSION", "sdk"),
        "adhocSignature": "LC_CODE_SIGNATURE" in headers,
        "dylibsUsed": [l.strip().split(" (")[0] for l in used.splitlines()[1:] if l.strip()],
        "sdkPath": str(sdk),
        "unverified": ["device load/run", "behaviour parity with a Theos build"],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = report["platform"] == "ios" and report["adhocSignature"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
