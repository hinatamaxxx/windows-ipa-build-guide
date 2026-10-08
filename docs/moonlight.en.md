# Build Moonlight iOS on Windows/WSL

[日本語](moonlight.md) | English

Compile the Moonlight iOS 9.0.2 application in WSL and package an unsigned IPA. Storyboards, assets, the Core Data model and generated classes are prepared first on a GitHub Actions macOS runner. You do not need your own Mac, but **this route is not fully local**.

The builder targets a [fixed Moonlight commit](https://github.com/moonlight-stream/moonlight-ios/tree/02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a), not arbitrary Xcode projects. On 2026-10-08 it produced IPAs from both upstream sources with the scene patch and sources with embedded Tailscale modifications. The Tailscale variant launched on iOS 27.0.1 / LiveContainer 3.8.0, but misplaced or incorrectly sized buttons and lists were reported. The layout remains unresolved and streaming is unverified. This guide does not include the Tailscale modifications or an IPA.

## Prepare the environment

Follow [setup](setup.en.md) to make Swift 6.4, the iPhoneOS 27.0 SDK and the pinned omarchy-apple-dev available to a normal WSL user. Reuse an existing environment. Python 3.12 or later, Git and GitHub CLI are also required. Run these commands in WSL.

```bash
git -c core.autocrlf=false clone --recursive \
  https://github.com/moonlight-stream/moonlight-ios.git "$HOME/moonlight-ios"
git -C "$HOME/moonlight-ios" checkout 02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a
git -C "$HOME/moonlight-ios" submodule update --init --recursive
git clone https://github.com/hinatamaxxx/windows-ipa-build-guide.git \
  "$HOME/windows-ipa-build-guide"
```

Work on the Linux filesystem and retain LF line endings. When copying modified sources from Windows, include uncommitted changes. Even a line-ending change in a resource causes the hash comparison to fail.

## Generate resources

Fork this guide into your GitHub account, enable Actions and manually run “Moonlight resource kit”. The workflow checks out unmodified public Moonlight sources at the pinned commit. It does not upload your local modifications or Apple SDK. Check your GitHub usage allowance and pricing.

```bash
gh workflow run moonlight-resources.yml --repo YOUR_ACCOUNT/windows-ipa-build-guide
gh run list --repo YOUR_ACCOUNT/windows-ipa-build-guide \
  --workflow moonlight-resources.yml --limit 5
# Use the ID of a successful run
gh run download RUN_ID --repo YOUR_ACCOUNT/windows-ipa-build-guide \
  --name moonlight-resource-kit-02dc978 --dir "$HOME/moonlight-kit-download"
mkdir -p "$HOME/moonlight-resource-kit"
tar -xzf "$HOME/moonlight-kit-download/moonlight-resource-kit.tar.gz" \
  -C "$HOME/moonlight-resource-kit"
```

Artifacts are retained for 30 days; regenerate them after expiry. Download from a successful run in a trusted fork and review the workflow that ran. Manifest hashes detect corruption and source mismatches; they do not authenticate the publisher.

The kit includes compiled screens, assets and models, generated Core Data code, an Info.plist template, a license and hashes. It excludes the app executable and Apple SDK. The verified resource build used Xcode 26.6 / iPhoneOS 26.5 SDK. Because `macos-latest` changes, each kit records the actual versions in `manifest.json`.

## Build the application

First apply the scene migration patch to the pinned upstream sources. Apps built with the iOS 27 SDK require the [UIKit scene lifecycle](https://developer.apple.com/documentation/technotes/tn3187-migrating-to-the-uikit-scene-based-life-cycle). The patch reuses the existing iPhone/iPad storyboards and does not enable multiple windows. Do not apply it twice to custom sources that already support scenes.

```bash
git -C "$HOME/moonlight-ios" apply --check \
  "$HOME/windows-ipa-build-guide/patches/moonlight-scene-lifecycle.patch"
git -C "$HOME/moonlight-ios" apply \
  "$HOME/windows-ipa-build-guide/patches/moonlight-scene-lifecycle.patch"
```

```bash
python3 "$HOME/windows-ipa-build-guide/scripts/build_moonlight.py" \
  --project "$HOME/moonlight-ios" \
  --resource-kit "$HOME/moonlight-resource-kit" \
  --omarchy "$HOME/omarchy-apple-dev-acd373c" \
  --output-dir "$HOME/ipa-deliveries"
```

Set `--omarchy` to the extracted [pinned commit](https://github.com/joshuaswarren/omarchy-apple-dev/tree/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942). A parser hash mismatch stops the build. Use `--sdk-bundle` and `--swift-bin` for non-default SDK or Swift paths.

The first build downloads the OpenSSL 3.6.3000 XCFramework and verifies its fixed SHA-256. Only its dynamic iOS arm64 framework is embedded in the IPA. The cache is `~/.cache/moonlight-ios-build`; simulator frameworks are not used.

If the source contains `TailscaleBridge`, the builder also runs its `build-apple.sh` and `go run ./cmd/notices`. This optional path was verified with Go 1.27.1. Review source and scripts before building. Unmodified upstream sources have no such directory, so Tailscale is not added to them.

## Output and verification scope

Each build creates a timestamped directory with an unsigned IPA, `verification.json`, `SHA256SUMS.txt` and `logs/`. Existing delivered IPAs are preserved. The target is arm64 with minimum iOS 15.0. The builder checks resource and source hashes, the OpenSSL hash and IPA ZIP CRC, and logs Mach-O headers and library dependencies.

For the verified artifact, the main executable and OpenSSL were also checked for the iOS platform, matching embedded framework paths and executable permissions. A successful build does not prove device compatibility. The upstream variant with only the scene patch has not been tested on a device. Import, signing, login, video, audio and input need separate device testing for each artifact.

Changing screens, assets or the data model invalidates the existing kit. Review the workflow's source reference and regenerate resources from the modified sources. Do not add private sources or credentials to a public workflow.

## Compilation details

The helper compiles Objective-C/C and Swift from the Xcode Sources lists and links the generated Core Data code. It specifies the original bridging header when generating Swift's Objective-C interface. Header paths are restricted to the required directories so FFmpeg's `time.h` does not shadow the SDK header. A cache-local symlink handles lowercase `openssl/` includes. The SDK is not modified.

The builder does not reproduce arbitrary Xcode settings or additional build phases. Review it when changing source structure or libraries. On failure, inspect the first failed compilation in `logs/`.

Moonlight and its bundled dependencies retain their respective licenses. Distributing a built artifact requires complying with those terms, including corresponding source provision where required.
