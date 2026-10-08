# Build iOS IPAs locally on Windows

[日本語](README.md) | English

This guide builds iOS artifacts on Windows with WSL2 and Arch Linux, without GitHub Actions or a Mac. It records two routes, each with a configuration that actually worked:

- Build an unsigned IPA from a Swift/xtool iOS app (verified with a SwiftUI Hello app)
- Build an Objective-C/C tweak dylib (optionally with a Go c-archive) without Theos, and swap it into an existing IPA (verified with a real jailed tweak; see [the dylib guide](docs/objc-dylib.en.md))

The guide covers environment setup and local builds only. It does not promise that an arbitrary Xcode project or tweak builds as is, and it does not cover signing, App Store distribution or installing directly on a stock iPhone. The output is unsigned.

## Verified configuration

On 2026-10-08 the sample was built on Windows 11 Pro, a Ryzen 7 7700, about 31 GiB of RAM and WSL2 Arch x86_64. Other CPUs, Windows on ARM, other Linux distributions and newer Swift/Xcode combinations have not been tested.

| Item | Verified version |
|---|---|
| WSL / Linux kernel | 3.0.1.0 / 6.18.40.1 |
| Swift / AUR package | 6.4 / swift-bin 6.4.0-2 |
| Apple SDK input | Xcode 27.xip from Apple |
| iPhoneOS SDK | 27.0 |
| omarchy-apple-dev | [`acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942`](https://github.com/joshuaswarren/omarchy-apple-dev/tree/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942) |
| xtool fork | `f0a1f90efdbb0dc023e276ff529da92618da7a87` |
| OpenAppleMacrosServer | `cb003a1763b08947dd37376ed8240cbfb4745c32` |
| rcodesign / ipsw / pymobiledevice3 | 0.29.0 / 3.1.731 / 11.24.0 |
| Go (for the tweak dylib's c-archive) | 1.27.1 |

Upstream describes its setup as needing no Mac. This guide built the Hello sample in the environment above and checked the structure of the IPA. In addition, the author loaded that IPA into LiveContainer, installed with AltStore Classic, and confirmed that it launches on a device. Installing and using LiveContainer is outside the scope of this guide.

## Getting started

1. Do the [first-time setup](docs/setup.en.md). Reuse an existing WSL, Swift and SDK if you have them.
2. As a normal user inside WSL, prepare an xtool project.
3. Check the environment and build with the helper script in this repository.

```bash
# GUIDE_DIR is the Linux-side directory where you cloned this guide
GUIDE_DIR="$HOME/windows-ipa-build-guide"
PROJECT_DIR="$HOME/HelloOmarchy"

python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

`--check` only reads the environment; it neither builds nor writes output files. It checks the Swift version, the SDK registration, the hashes of the pinned upstream scripts (`ship.sh` and `tools/asc.py`) and of the SwiftBuild fix, and that the Python venv used by `ship.sh` works.

The build runs the pinned `ship.sh --device` as the normal user. With this argument the upstream script only builds and lays out resources; it does not touch any device. `ship.sh` without arguments creates a persistent TEST signing identity, so this guide does not use it.

This route targets Swift iOS apps that have `Package.swift` and `xtool.yml`. Review the project's code before building, including `xtool.env` and SwiftPM plugins, which run during the build. If dependencies need resolving, the build may access the network. To convert an existing Xcode project, see upstream's conversion tool and check compatibility per project.

Objective-C/C tweak dylibs are built in the same environment with `scripts/build_objc_dylib.py` and swapped into an existing IPA with `scripts/replace_ipa_file.py`. Requirements and steps are in [the dylib guide](docs/objc-dylib.en.md).

## Output and verification

Each build creates a new timestamped directory under `ipa-deliveries` containing `<App>-unsigned.ipa`, `verification.json` and `build.log`. Existing delivered IPAs are never overwritten. The project's build cache and `xtool/*.app` are updated by every build.

`ship.sh` only processes the first `.app` it finds in `xtool/`, so the helper stops before building when `xtool/` holds two or more `.app` directories. If an old `.app` is left over, for example after renaming the app, move it out of `xtool/` and build again. Use `--app-name` to check that the built app has the expected name.

The verification JSON records the Payload layout, the ZIP CRC, the Bundle ID, the version and build numbers, whether the main executable and extensions target arm64/iOS, the absence of signatures and provisioning, and SHA-256 hashes. It does not verify the compatibility of every embedded library, Apple's signature checks or behaviour on a device.

If you do not set a build number (CFBundleVersion), `ship.sh` derives one from the UTC build time. To get the same number every time, set it with an environment variable, for example `BUILD_NUMBER=1 python3 ...`.

The version in SDKSettings.json and the SDK field in the Mach-O header are recorded separately. For the verified sample the SDK used was 27.0 and the header's SDK field was 17.0.0. This route does not rewrite metadata for the App Store.

## Day-to-day builds and updates

Day to day you only run `--check` and the build. Do not reinstall Swift, the SDK or the upstream installer. When the hashes of Swift or the upstream scripts change, the helper stops and asks you to recheck compatibility. Adopt a new version only after confirming the matching Xcode, the compatibility fix and a sample build.

Arch is a rolling-release distribution. After running `sudo pacman -Syu`, check the environment with `--check` first. When Python's minor version changes, the `~/pymobile3-venv` used by `ship.sh` stops working. swift-bin is an AUR package, so `pacman -Syu` does not update it, but the libraries it depends on are updated. The fix is in [the recovery section of the setup guide](docs/setup.en.md#recovery-and-reuse).

The same recovery section explains how to resume when the first-time setup stops after the SDK is registered, and covers common errors. Deleting files inside WSL may not shrink the VHD on Windows.

## Data and license

This repository does not distribute Apple's SDK, Xcode.xip, IPAs, signing keys or account information. Obtain Apple's software yourself through official channels and check the terms that apply. This guide does not change Apple's terms or distribution requirements. Delivering files to iCloud or elsewhere is a separate step from the build.

The documents and helper scripts written for this repository are under the [MIT License](LICENSE). Upstream code is neither copied nor bundled; pinned commits are referenced instead. The [omarchy-apple-dev license](https://github.com/joshuaswarren/omarchy-apple-dev/blob/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942/LICENSE) and the terms of each dependency and of Apple's software apply independently.

Writing assistance for the documents and helper scripts: Codex (GPT-6.1 Sol, reasoning setting not recorded). Proofreading of the published Japanese documents: Gemini 3.8 Flash / High. Review, revision and English translation: Claude Code (Claude Opus 5.5).
