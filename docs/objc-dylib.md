# Objective-C/Cのtweak dylibと既存IPAの差し替え

Swift/xtoolアプリのほかに、Objective-CやC（必要ならGoのc-archive）で書かれたjailed（サイドロード用）tweak dylibも、同じWSL環境でビルドできます。TheosやMacは使いません。使うのは、[初回の環境構築](setup.md)で準備したSwiftのclang、darwin Swift SDK内のiPhoneOS SDKと `ld64.lld`、SDKに含まれるXcodeツールチェーンの `libclang_rt.ios.a` です。

2026-10-08に、実在のjailed tweakのdylibをこの手順でビルドしました。CIのTheos版と比べ、依存ライブラリの組とシンボルが一致することを確認しています。作ったdylibを既存のIPAへ差し替えて、IPAを書き出すところまで成功しました。実機での読み込みは、このガイドでは確認していません。

## 対象になる条件

- ソースが `.m` と `.c` だけで、Logos（`.x` / `.xm`）を使わないこと。Makefileが `library.mk` や `tweak.mk` を使っていてもかまいません。Logosを使う場合はTheosのプリプロセッサが必要なので、この手順の対象外です。
- arm64だけで足りること。arm64eのビルドとPAC用の検証はしていません。
- 既存IPAに、そのdylibを読み込む `LC_LOAD_DYLIB` が既にあり、中身を差し替えるだけで済むこと。新しいdylibを読み込ませるにはロードコマンドの追加（insert_dylibなど）が別に必要で、`replace_ipa_file.py` はこの操作を行いません。

元にするIPAは、本人が正当な経路で用意してください。このガイドはIPAやアプリのバイナリを配布しません。復号済みIPAなど第三者のバイナリを、GitHubなどの外部サービスへ送らないでください。

## 手順

1. ソースはWSL側にLF改行で取得します。WindowsでチェックアウトしたCRLFのファイルをそのまま使わないでください。サブモジュールがあれば固定コミットに合わせます。
2. プロジェクトに準備用のスクリプトがあれば、WSLの `python3` で実行します。
3. `build_objc_dylib.py --check` で道具がそろっているかを確かめます。
4. Makefileの `*_FILES`、`*_CFLAGS`、`*_FRAMEWORKS`、`*_LIBRARIES`、`-install_name` を、`build_objc_dylib.py` の引数に書き写してビルドします。Goのc-archiveがある場合は、`--go-package` を指定すると先にc-archiveを作り、自動でリンクします。
5. 出力された `report.json` で、`platform` が `ios`、`adhocSignature` が `true` であることと、`minos` と `dylibsUsed` の値を確かめます。比較できる既存のビルド（CIの成果物など）があれば、`llvm-objdump --macho --dylibs-used` と `--syms` の結果を比べます。
6. `replace_ipa_file.py` で、dylibを差し替えた新しいIPAを書き出します。元のIPAは読むだけで、出力先に同名のファイルがあれば上書きせずに停止します。

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
python3 "$GUIDE_DIR/scripts/build_objc_dylib.py" --check
python3 "$GUIDE_DIR/scripts/build_objc_dylib.py" --project "$HOME/MyTweak" --name MyTweak \
  --source Tweak.m --cflag=-fobjc-arc --framework Foundation --framework UIKit \
  --install-name @rpath/MyTweak.dylib --output-dir "$HOME/dylib-out"
python3 "$GUIDE_DIR/scripts/replace_ipa_file.py" --ipa '/path/to/base.ipa' \
  --entry 'Payload/App.app/Frameworks/MyTweak.dylib' \
  --file "$HOME/dylib-out/<日時付きディレクトリ>/MyTweak.dylib" --output '/path/to/new.ipa'
```

`build_objc_dylib.py` は、日時付きのディレクトリを新しく作り、その中にdylib、`report.json`、`build.log` を保存します。dylibには、リンカーの `-adhoc_codesign` でad-hoc署名だけを付けます（Theosの `ldid -S` に相当）。署名IDの作成、実機へのインストール、ログインは行いません。

`replace_ipa_file.py` はWindowsのPythonでもWSLのPythonでも動きます。差し替えたエントリは元のUnixモード（dylibなら0755）を保ちます。Windowsのzip処理でモードが落ちたエントリは、Mach-Oなら0755、それ以外は0644に戻します。結果のJSONで、エントリのハッシュが差し替えたファイルと一致することと、エントリ数が元のIPAと同じことを確かめてください。

## 詰まった点と対処

次の対処は、どれも補助スクリプトに組み込んであります。ただし、フレームワークの追加はプロジェクトごとに引数で指定します。

| 症状 | 原因 | 対処 |
|---|---|---|
| `ld64.lld: must specify -platform_version` / `missing -arch arm64` | Linux上のclangがリンカーをld64互換と判断せず、引数を渡さない | `-mlinker-version=907` を付ける |
| `undefined symbol: __isPlatformVersionAtLeast` | `@available` の実行時判定に必要なdarwin用compiler-rtが、Linux版Swiftツールチェーンにない | SDKバンドル内Xcodeツールチェーンの `libclang_rt.ios.a` をリンクする |
| `undefined symbol: kCACornerCurveContinuous` | Theosのフレームワーク指定にない `QuartzCore` を使っていた | `--framework QuartzCore` を足す |
| プロジェクトのライセンス表記スクリプトが `/usr/lib/go/LICENSE` で失敗する | ArchのGoはLICENSEを `/usr/share/licenses/go/` に置く | dylibのビルドには関係しない。同梱表記が必要なら別に作る |
| Git Bashから `wsl.exe ... bash /mnt/c/...` を実行するとWindowsのパスに変わる | MSYSのパス変換 | `MSYS_NO_PATHCONV=1` を付ける。`$変数` を含むコマンドは、スクリプトファイルにしてから渡す |
| PowerShellや.NETの `ZipArchive` で差し替えたIPAの実行ファイルが `-rw----` になる | .NETが更新時にセントラルディレクトリを作り直し、Unixモードを落とす | .NETでIPAを書き換えない。`replace_ipa_file.py` は落ちたモードを戻す |
| iCloud Driveに書き出した直後の改名が `WinError 32` で失敗する | 同期クライアントが一時的にファイルをつかむ | 改名を最大30秒再試行する |
