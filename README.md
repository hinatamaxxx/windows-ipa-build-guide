# WindowsでSwift iOSアプリのIPAをローカル生成する

Windows上のWSL2とArch Linuxを使い、Swift/xtool対応のiOSアプリをビルドする手順です。GitHub ActionsやMacを使わずに、SwiftUIのHelloアプリから未署名IPAを生成できた構成を記録しています。

このガイドで扱うのは、環境構築とローカルビルドです。任意のXcodeプロジェクトがそのまま動くことは保証しません。署名、App Store配布、通常のiPhoneへの直接インストールの手順も含みません。生成物は未署名です。

## 検証した構成

2026-10-08に、Windows 11 Pro、Ryzen 7 7700、約31GiB RAM、WSL2 Arch x86_64でサンプルをビルドしました。別のCPU、Windows ARM、他のLinuxディストリビューション、新しいSwiftとXcodeの組み合わせは未検証です。

| 項目 | 検証済み版 |
|---|---|
| WSL / Linuxカーネル | 3.0.1.0 / 6.18.40.1 |
| Swift / AURパッケージ | 6.4 / swift-bin 6.4.0-2 |
| Apple SDK入力 | Apple公式から取得したXcode 27.xip |
| iPhoneOS SDK | 27.0 |
| omarchy-apple-dev | [`acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942`](https://github.com/joshuaswarren/omarchy-apple-dev/tree/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942) |
| xtool fork | `f0a1f90efdbb0dc023e276ff529da92618da7a87` |
| OpenAppleMacrosServer | `cb003a1763b08947dd37376ed8240cbfb4745c32` |
| rcodesign / ipsw / pymobiledevice3 | 0.29.0 / 3.1.731 / 11.24.0 |

上流は「Mac不要」と説明しています。このガイドでは、上記の環境でHelloサンプルをビルドし、IPAの構造を検証しました。さらに作者が、AltStore Classicで導入したLiveContainerにこのIPAを読み込み、端末上で起動することを確認しています。LiveContainerの導入と使い方は、このガイドでは扱いません。

## 使い始める

1. [初回の環境構築](docs/setup.md)を行います。既存のWSL、Swift、SDKがあれば再利用します。
2. WSL内の通常ユーザーで、xtool対応プロジェクトを用意します。
3. このリポジトリの自作補助スクリプトで、環境を確認してからビルドします。

```bash
# GUIDE_DIRはこのガイドをcloneしたLinux側ディレクトリ
GUIDE_DIR="$HOME/windows-ipa-build-guide"
PROJECT_DIR="$HOME/HelloOmarchy"

python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

`--check` は環境を読み取るだけで、ビルドも出力ファイルの作成もしません。Swiftの版、SDKの登録、固定版の上流スクリプト（`ship.sh` と `tools/asc.py`）とSwiftBuild修正のハッシュ、`ship.sh` が使うPython venvの動作を確かめます。

ビルドでは、通常ユーザーで固定版の `ship.sh --device` を実行します。上流スクリプトはこの引数のとき、ビルドとリソース配置だけを行い、端末を操作しません。引数なしの `ship.sh` は永続的なTEST署名IDを作るため、このガイドでは使いません。

対象プロジェクトは、`Package.swift` と `xtool.yml` を持つSwift iOSアプリです。ビルド中に実行される `xtool.env` やSwiftPMプラグインも含め、プロジェクトのコードを確認してからビルドしてください。依存の解決が必要なら、ビルド中にネットワークへアクセスすることがあります。既存のXcodeプロジェクトを変換する場合は上流の変換ツールを参照し、プロジェクトごとに互換性を確認します。

## 出力と検証

`ipa-deliveries` に日時付きのディレクトリが新しく作られ、その中に `<App>-unsigned.ipa`、`verification.json`、`build.log` が生成されます。既存の納品IPAは上書きしません。プロジェクト内のビルドキャッシュと `xtool/*.app` は、ビルドのたびに更新されます。

`ship.sh` は `xtool/` で最初に見つかった `.app` だけを処理します。そのため補助スクリプトは、ビルド前の `xtool/` に `.app` が2つ以上あると停止します。アプリ名を変えた後などに古い `.app` が残っていたら、`xtool/` の外へ移してからビルドします。`--app-name` は、ビルドされたアプリの名前が期待どおりかを確かめるときに使います。

検証JSONには、Payload構造、ZIP CRC、Bundle ID、版とビルド番号、主実行ファイルと拡張がarm64/iOS向けか、署名とプロビジョニングがないこと、SHA-256を記録します。内蔵ライブラリすべての互換性、Appleの署名検証、実機での動作は検証しません。

ビルド番号（CFBundleVersion）は、指定しなければ `ship.sh` がビルド時のUTC時刻から作ります。毎回同じ番号にしたい場合は、`BUILD_NUMBER=1 python3 ...` のように環境変数で指定します。

SDKSettings.jsonのバージョンと、Mach-OヘッダーのSDK欄は別々に記録します。検証したサンプルでは、使用したSDKは27.0、ヘッダーのSDK欄は17.0.0でした。この経路では、App Store用のメタデータを書き換えません。

## 日常のビルドと更新

毎回の作業は `--check` とビルドだけです。Swift、SDK、上流インストーラーを再導入しないでください。Swiftや上流スクリプトのハッシュが変わると、補助スクリプトは互換性の再確認を求めて停止します。新しい版は、対応するXcode、互換修正、サンプルのビルドを確かめてから採用してください。

Archは常に最新版へ更新するディストリビューションです。`sudo pacman -Syu` を実行した後は、まず `--check` で環境を確かめてください。Pythonのマイナー版が上がると、`ship.sh` が使う `~/pymobile3-venv` が動かなくなります。swift-binはAURパッケージなので `pacman -Syu` では更新されませんが、依存するライブラリは更新されます。直し方は[構築手順の復旧節](docs/setup.md#復旧と再利用)にあります。

SDK登録後に初回構築が途中で止まった場合の再開方法と、よくあるエラーも同じ復旧節にまとめています。WSL内でファイルを削除しても、Windows上のVHDのサイズは縮まらないことがあります。

## データとライセンス

AppleのSDK、Xcode.xip、IPA、署名鍵、アカウント情報は配布していません。Appleの配布物は本人が公式の経路で取得し、適用される規約を確認してください。このガイドはAppleの規約や配布要件を変更しません。iCloudなどへの納品は、ビルドとは別の操作です。

本リポジトリの自作文書と補助スクリプトは [MIT License](LICENSE) です。上流のコードは転載も同梱もせず、固定commitを参照します。[omarchy-apple-devのライセンス](https://github.com/joshuaswarren/omarchy-apple-dev/blob/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942/LICENSE)と、各依存やAppleの配布物の条件は、それぞれ独立しています。

文書・自作補助スクリプトの作成支援: Codex（GPT-6.1 Sol、推論設定は未記録）。公開文書の校正: Gemini 3.8 Flash / High。見落としの点検と改訂: Claude Code（Claude Opus 5.5）。
