# First-time setup

[日本語](setup.md) | English

The commands on this page are marked as either Windows-side or WSL-side. Read the pinned versions of community code from the AUR and GitHub before running them. No OS reinstall, disk wipe or firewall change is needed.

## 1. WSL2 and Arch Linux

First, in Windows PowerShell, check the existing environment and free space.

```powershell
wsl --list --verbose
wsl --version
Get-PSDrive -PSProvider FileSystem
Get-CimInstance Win32_Processor | Select-Object Name,VirtualizationFirmwareEnabled
```

Counting the XIP, the extracted SDK, the registered SDK copy and Swift's build cache, 50 GiB or more of free space makes the work comfortable. In the verified environment the extraction used about 12 GiB and the registered copy about 13 GiB. Larger projects need more.

If WSL is not installed, install it the official way from an administrator PowerShell.

```powershell
wsl --install --no-distribution
```

If Windows asks for a restart, save your work and restart yourself. If WSL is already installed, update it first with `wsl --update`. With an old WSL, Arch does not appear in the distribution list used by `wsl --install archlinux` below.

Next, get the official Arch Linux. If the same distribution already exists, do not install it again.

```powershell
wsl --update
wsl --install archlinux
wsl --list --verbose
```

By default WSL can use half of the physical memory. The verified machine had about 31 GiB of RAM. If builds such as xtool's are killed partway on a machine with less memory, add swap or raise the memory limit in `%UserProfile%\.wslconfig` on Windows. Choose values for your machine, and restart WSL with `wsl --shutdown` after the change.

```ini
[wsl2]
swap=16GB
```

References: [Basic WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands), [Advanced WSL settings](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [Arch Linux downloads](https://archlinux.org/download/).

## 2. A normal user and official dependencies

If Arch starts as root, create a normal user. Replace `builder` below with any Linux user name. Open `wsl -d archlinux --user root` from Windows and run the commands inside WSL. Enter the password yourself.

The WSL build of Arch may not include `sudo` or a text editor. In that case, run `pacman -Syu sudo nano` in this root session first to install them from the official packages.

```bash
useradd -m -G wheel -s /bin/bash builder
passwd builder
printf '%%wheel ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/90-wheel-password
chmod 0440 /etc/sudoers.d/90-wheel-password
visudo -cf /etc/sudoers
```

If the user or the sudo configuration already exists, do not recreate it. Then open the configuration file with `nano /etc/wsl.conf`. Keep the existing content and set these two items in the matching sections.

```ini
[boot]
systemd=true

[user]
default=builder
```

In Windows PowerShell, shut down only this distribution and reopen it as the normal user. Save any unsaved work inside WSL first.

```powershell
wsl --terminate archlinux
wsl -d archlinux -- id
```

From here on, builds run as the normal user. Inside WSL, install only the official Arch dependencies that are missing.

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel git zip unzip less libimobiledevice openssl \
  poppler libheif python pkgconf go patchelf libxml2-legacy libedit librsvg
```

## 3. Getting this guide

On this public repository's GitHub page, copy the clone URL from **Code → HTTPS**. Run the following inside WSL and paste the URL when asked. If you already have it, skip the clone and point `GUIDE_DIR` at that directory.

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
read -r -p 'HTTPS clone URL of this guide: ' GUIDE_URL
git clone "$GUIDE_URL" "$GUIDE_DIR"
```

The shell variables set here and the `export PATH` later only last for that WSL session, so each later section sets the variables it needs again. The day-to-day helper script sets the PATH it needs itself, so you do not have to change your shell configuration permanently.

## 4. Swift 6.4

The verified AUR recipe is `swift-bin` 6.4.0-2 at commit `76ec647c95acf2d46b6f0b235660084d0bd69eb2`. It wraps the official Swift tarball, but the recipe itself is community code. Check its content, sources and hashes, then build the package as the normal user.

```bash
mkdir -p "$HOME/build-sources"
git clone https://aur.archlinux.org/swift-bin.git "$HOME/build-sources/swift-bin"
cd "$HOME/build-sources/swift-bin"
git checkout --detach 76ec647c95acf2d46b6f0b235660084d0bd69eb2
git rev-parse HEAD
less PKGBUILD
makepkg -si
export PATH="/usr/lib/swift/usr/bin:$HOME/.local/bin:$PATH"
swift --version
```

The SHA-256 of the verified official Swift tarball is `50863678e3bafd91fcbc94c0bb76610bab37c1ee01e335fc7d8616904e03e19a`. Confirm in the PKGBUILD that the recipe checks its input against this hash. yay is not needed for normal builds. yay 13.0.1 was also installed in the verified environment, but these steps use the pinned AUR recipe directly.

## 5. Pinned upstream and the SwiftBuild fix

Clone upstream inside WSL so that Windows CRLF line endings do not get mixed in. Do not overwrite an existing directory; reuse it if it is at the same commit.

```bash
OMARCHY_COMMIT=acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942
OMARCHY_DIR="$HOME/omarchy-apple-dev-acd373c"
git clone https://github.com/joshuaswarren/omarchy-apple-dev.git "$OMARCHY_DIR"
git -C "$OMARCHY_DIR" checkout --detach "$OMARCHY_COMMIT"
git -C "$OMARCHY_DIR" rev-parse HEAD
less "$OMARCHY_DIR/install-toolchain.sh"
```

With Swift 6.4, upstream's installer tries to write root-owned xcspec files even with `--user-only`. The helper script in this repository checks the known original hashes and then changes only the four values in these three files. Files already fixed are left alone, and anything with different content stops the script.

| File under `/usr/lib/swift/usr/share/pm/` | Change |
|---|---|
| `SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec` | Input encoding `$(InputFileTextEncoding)` → `utf-8` (1 place) |
| `SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec` | Output encoding `UTF-16` → `binary` (2 places) |
| `SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec` | Output encoding `UTF-16` → `binary` (1 place) |

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --check
# Read the plan before applying. Use a backup directory that does not exist yet.
sudo python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --apply \
  --backup "$HOME/SwiftBuild-originals-$(date -u +%Y%m%dT%H%M%SZ)"

# Generate a local variant that keeps upstream's original and does not rewrite the fixed xcspec files
python3 "$GUIDE_DIR/scripts/prepare_installer.py" --repo "$OMARCHY_DIR"
```

The variant is written to `$OMARCHY_DIR/install-toolchain-wsl-guarded.sh`, and the original `install-toolchain.sh` stays as it is. Only one statement differs: the step that writes the fixed xcspec files is replaced with a check that their content matches.

Root is used only for fixing these three files and installing official dependencies. There is no need to widen the normal user's write permissions or to run the whole installer as root. Keep the backup; do not delete it. Because it is created with sudo, the backup is owned by root and the normal user cannot delete it.

## 6. Apple's Xcode and importing the SDK

Download Xcode 27.xip, which matches Swift 6.4, yourself from [Apple Developer Downloads](https://developer.apple.com/download/all/?q=Xcode). Signing in, accepting the terms and confirming that you may download it are up to you. Do not use SDKs distributed by third parties, and do not add the XIP or the extracted SDK to this repository.

The verified Xcode_27.xip is 2,014,229,334 bytes with SHA-256 `6a270c53a5a0c5e0ac78125342d44c3cfff2716ec390373cd5e30834d80a67c3`. Do not use these values for other versions. This comparison only confirms that the download source and the file content match; it is not an independent check of Apple's signature on the XIP.

Convert the real path of the XIP on Windows to a WSL path by running `wslpath -u 'C:\path\to\Xcode_27.xip'` inside WSL. Then run the following inside WSL.

```bash
OMARCHY_DIR="$HOME/omarchy-apple-dev-acd373c"
export PATH="/usr/lib/swift/usr/bin:$HOME/.local/bin:$PATH"
sha256sum '/mnt/c/path/to/Xcode_27.xip'
# Import only after confirming the official source, the version and the hash above
XCODE_XIP='/mnt/c/path/to/Xcode_27.xip' \
  bash "$OMARCHY_DIR/install-toolchain-wsl-guarded.sh" --user-only
swift sdk list
```

On success, `darwin` is registered and the SDK is created at `$HOME/.swiftpm/swift-sdks/darwin.artifactbundle`. The pinned installer prepares xtool, rcodesign, ipsw, pymobiledevice3, actool and other tools inside the SDK, and OpenAppleMacrosServer. According to upstream's comments, the first run takes about 7 minutes to build xtool and about 5 minutes to build OpenAppleMacrosServer, plus the time to extract the SDK. Re-extracting the SDK costs time and space, so if the setup stops partway, first check whether the SDK is already registered.

Upstream installs pymobiledevice3 with pip without pinning a version. The version at verification time was 11.24.0. To use exactly that version, after the initial setup run `"$HOME/pymobile3-venv/bin/python" -m pip install 'pymobiledevice3==11.24.0'` inside the existing venv only. This guide does not use pymobiledevice3 for device or account operations.

## 7. Sample IPA and day-to-day builds

In a free directory, create the sample without the authentication setup.

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
cd "$HOME"
"$HOME/.local/bin/xtool" new HelloOmarchy --skip-setup
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

When a new output directory contains the unsigned IPA, the verification JSON and the log, local generation is confirmed. To build another supported project, change `--project`. If you put upstream elsewhere, pass `--repo "$OMARCHY_DIR"`. Do not redo the initial installation of the SDK and Swift every time.

### SVG icons and the recorded SDK version

Asset catalogs containing SVGs require `rsvg-convert`, provided by the `librsvg` package above. If the build reports `Failed to rasterise SVG asset` and `rsvg-convert: No such file or directory`, run `sudo pacman -S --needed librsvg` inside WSL, check `rsvg-convert --version`, then rebuild as the regular user.

In this environment, a build using the iPhoneOS 27.0 SDK can record 17.0, the minimum OS version, in the executable's SDK field. Check both `source_sdk_version` and `macho_sdk_version` in the verification JSON. This difference matters when an app uses newer system appearance behavior tied to its linked SDK.

For a SwiftPM target with minimum OS 17.0 and SDK 27.0, the following linker settings have been verified to record SDK 27.0 in the executable. The values must match the SDK actually used; this check does not replace device testing. Review them when updating the SDK.

```swift
linkerSettings: [.unsafeFlags([
    "-Xlinker", "-platform_version", "-Xlinker", "ios",
    "-Xlinker", "17.0", "-Xlinker", "27.0"
])]
```

## Recovery and reuse

- If an xcspec raises `PermissionError`, check the original and fixed hashes of the three files above, and use the backed-up compatibility fix and the variant installer. Do not run the whole installer as root.
- If the remaining tool setup fails after the SDK is registered, check `swift sdk list` and that the SDK exists, then resume from the failed step through the normal `--user-only` route. `--repair` unregisters the SDK and starts over, so do not use it for a normal resume.
- If only OpenAppleMacrosServer is unfinished, you can rebuild it from the pinned source as the normal user with `swift build -c release --build-system native --static-swift-stdlib --product OpenAppleMacrosServer --jobs 4`. Check the placement steps in upstream's `install_oam`, back up the original server in the SDK, then put the result in place. No signing key or device setting is needed.
- If builds fail only after changing the SDK, build from a fresh copy of the sources to find out whether a stale module cache is the cause. Do not delete the whole project.
- If `--check` reports a hash mismatch, the current version differs from the pinned one. Do not remove the check or force an old compatibility patch without finding the cause.
- If `--check` stops with `pymobile3-venv cannot import cryptography`, Python's version has probably changed through `pacman -Syu`. Recreate the venv with `python3 -m venv --clear "$HOME/pymobile3-venv"` and reinstall with `"$HOME/pymobile3-venv/bin/pip" install 'pymobiledevice3==11.24.0'`.
- If `--check` reports a changed Swift version or SwiftBuild fix hash, swift-bin may have been reinstalled or affected by a library update. Until compatibility is confirmed, you can hold the package with `IgnorePkg` in `/etc/pacman.conf`.
- If `ship.sh` stops with `unresolved $(...) placeholders`, the Info.plist still contains team-ID placeholders such as `$(AppIdentifierPrefix)`. The helper script does not pass a team ID, so projects in this state cannot be built through this route.
- If the helper stops with `Several apps under xtool/`, an old `.app` is left in `xtool/`. Move the unneeded `.app` out of `xtool/` and build again.
- The missing `libpython3.12` for LLDB did not affect building the verified sample IPA. Check the matching dependency when you use debugging separately.

When you no longer need the environment, deleting the WSL distribution removes every file on the Linux side. Before running `wsl --unregister`, move the sources, outputs and backups you need to a safe place yourself. This guide never deletes anything automatically.
