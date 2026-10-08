# Objective-C/C tweak dylibs and swapping them into an existing IPA

[日本語](objc-dylib.md) | English

Besides Swift/xtool apps, the same WSL environment can build jailed (sideloading) tweak dylibs written in Objective-C or C, optionally with a Go c-archive. Neither Theos nor a Mac is used. The tools are the ones prepared in the [first-time setup](setup.en.md): Swift's clang, the iPhoneOS SDK and `ld64.lld` in the darwin Swift SDK, and `libclang_rt.ios.a` from the Xcode toolchain inside the SDK.

On 2026-10-08 a real jailed tweak's dylib was built with these steps. Compared with the CI build made with Theos, the set of linked libraries and the symbols matched. The new dylib was swapped into an existing IPA and the IPA was written out successfully. Loading on a device has not been verified in this guide.

## Requirements

- The sources are `.m` and `.c` only and do not use Logos (`.x` / `.xm`). A Makefile based on `library.mk` or `tweak.mk` is fine. Logos needs Theos's preprocessor and is out of scope.
- arm64 is enough. arm64e builds and PAC have not been tested.
- The existing IPA already has an `LC_LOAD_DYLIB` for that dylib, so only its contents need replacing. Loading a new dylib requires adding a load command (insert_dylib or similar), which `replace_ipa_file.py` does not do.

Obtain the base IPA yourself through legitimate means. This guide does not distribute IPAs or app binaries. Do not upload third-party binaries, such as decrypted IPAs, to GitHub or other external services.

## Steps

1. Check out the sources inside WSL with LF line endings. Do not use files checked out on Windows with CRLF. Pin submodules to their recorded commits.
2. If the project has a preparation script, run it with WSL's `python3`.
3. Check the tools with `build_objc_dylib.py --check`.
4. Copy the Makefile's `*_FILES`, `*_CFLAGS`, `*_FRAMEWORKS`, `*_LIBRARIES` and `-install_name` into the arguments of `build_objc_dylib.py` and build. If there is a Go c-archive, `--go-package` builds it first and links it automatically.
5. In the generated `report.json`, check that `platform` is `ios` and `adhocSignature` is `true`, and look at `minos` and `dylibsUsed`. If you have an existing build to compare with (such as a CI artifact), compare the output of `llvm-objdump --macho --dylibs-used` and `--syms`.
6. Write a new IPA with the dylib replaced by `replace_ipa_file.py`. The base IPA is only read, and the script stops instead of overwriting when the output file already exists.

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
python3 "$GUIDE_DIR/scripts/build_objc_dylib.py" --check
python3 "$GUIDE_DIR/scripts/build_objc_dylib.py" --project "$HOME/MyTweak" --name MyTweak \
  --source Tweak.m --cflag=-fobjc-arc --framework Foundation --framework UIKit \
  --install-name @rpath/MyTweak.dylib --output-dir "$HOME/dylib-out"
python3 "$GUIDE_DIR/scripts/replace_ipa_file.py" --ipa '/path/to/base.ipa' \
  --entry 'Payload/App.app/Frameworks/MyTweak.dylib' \
  --file "$HOME/dylib-out/<timestamped-directory>/MyTweak.dylib" --output '/path/to/new.ipa'
```

`build_objc_dylib.py` creates a new timestamped directory and saves the dylib, `report.json` and `build.log` there. The dylib only gets an ad-hoc signature from the linker's `-adhoc_codesign` (the equivalent of Theos's `ldid -S`). No signing identity is created, nothing is installed on a device, and no sign-in happens.

`replace_ipa_file.py` runs with either Windows or WSL Python. The replaced entry keeps its original Unix mode (0755 for a dylib). Entries whose mode was dropped by a Windows zip tool get 0755 back if they are Mach-O files and 0644 otherwise. In the resulting JSON, check that the entry's hash matches the replacement file and that the entry count equals that of the base IPA.

## Problems hit and fixes

All of these fixes are built into the helper scripts, except that extra frameworks are passed as arguments per project.

| Symptom | Cause | Fix |
|---|---|---|
| `ld64.lld: must specify -platform_version` / `missing -arch arm64` | clang on Linux does not treat the linker as ld64-compatible and does not pass these arguments | Add `-mlinker-version=907` |
| `undefined symbol: __isPlatformVersionAtLeast` | The darwin compiler-rt needed for the runtime check of `@available` is missing from the Linux Swift toolchain | Link `libclang_rt.ios.a` from the Xcode toolchain in the SDK bundle |
| `undefined symbol: kCACornerCurveContinuous` | The code used `QuartzCore`, which the Theos framework list did not include | Add `--framework QuartzCore` |
| The project's license-notice script fails on `/usr/lib/go/LICENSE` | Arch's Go package puts LICENSE in `/usr/share/licenses/go/` | Unrelated to building the dylib; create the notice separately if you need to ship it |
| Running `wsl.exe ... bash /mnt/c/...` from Git Bash turns the path into a Windows path | MSYS path conversion | Set `MSYS_NO_PATHCONV=1`. Put commands containing `$variables` into a script file and pass that |
| Executables in an IPA rewritten with PowerShell/.NET `ZipArchive` become `-rw----` | .NET rebuilds the central directory on update and drops the Unix modes | Do not rewrite IPAs with .NET. `replace_ipa_file.py` restores dropped modes |
| Renaming right after writing to iCloud Drive fails with `WinError 32` | The sync client briefly holds the file | Retry the rename for up to 30 seconds |
