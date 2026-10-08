# WindowsでSwift iOSアプリのIPAをローカル生成する

Windows上のWSL2とArch Linuxを使い、Swift/xtool対応のiOSアプリをビルドする手順です。GitHub ActionsやMacを使わず、SwiftUIのHelloアプリから未署名IPAを生成できた構成を記録しています。

これは環境構築とローカルビルドのガイドです。任意のXcodeプロジェクトがそのまま動く保証や、署名・App Store配布・通常のiPhoneへの直接インストール手順は含みません。生成物は未署名です。

## 検証した構成

2026-10-08に、Windows 11 Pro、Ryzen 7 7700、約31GiB RAM、WSL2 Arch x86_64でサンプルをビルドしました。別のCPU、Windows ARM、他のLinuxディストリビューション、新しいSwift/Xcodeの組み合わせは未検証です。

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

上流の「Mac不要」という説明に対し、このガイドで実際に確認した範囲は、上記環境でのHelloサンプルのビルドとIPA構造検証です。端末での起動成功という利用者報告はありますが、端末側の署名・導入経路は確認していません。

## 使い始める

1. [初回の環境構築](docs/setup.md)を行います。既存のWSL、Swift、SDKがあれば再利用します。
2. WSL内の通常ユーザーで、xtool対応プロジェクトを用意します。
3. このリポジトリの自作補助スクリプトで、環境確認とビルドを行います。

```bash
# GUIDE_DIRはこのガイドをcloneしたLinux側ディレクトリ
GUIDE_DIR="$HOME/windows-ipa-build-guide"
PROJECT_DIR="$HOME/HelloOmarchy"

python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$PROJECT_DIR" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

`--check` は環境を読み取るだけです。ビルドは通常ユーザーで固定版 `ship.sh --device` を実行します。上流スクリプトのこの引数はビルドとリソース配置だけを行い、端末の操作を実行しません。引数なしの `ship.sh` は永続TEST署名IDを作るため、このガイドでは使いません。

対象プロジェクトは `Package.swift` と `xtool.yml` を持つSwift iOSアプリです。実行される `xtool.env` やSwiftPMプラグインを含め、プロジェクトのコードを確認してからビルドしてください。依存解決が必要ならビルド中にネットワークアクセスが発生することがあります。既存Xcodeプロジェクトの変換は上流の変換ツールを参照し、プロジェクトごとに互換性を確認します。

## 出力と検証

`ipa-deliveries` の新しい日時付きディレクトリに、`<App>-unsigned.ipa`、`verification.json`、`build.log` が生成されます。既存の納品IPAは上書きしません。プロジェクト内のビルドキャッシュと `xtool/*.app` はビルドによって更新されます。

検証JSONには、Payload構造、ZIP CRC、Bundle ID、版/ビルド番号、主実行ファイルと拡張のarm64/iOS判定、署名・プロビジョニングの不在、SHA-256を記録します。すべての内蔵ライブラリの互換性、Appleの署名検証、実機の動作は検証しません。

SDKSettings.jsonのバージョンと、Mach-OヘッダーのSDK欄は別々に記録します。検証したサンプルでは使用SDKは27.0、ヘッダーのSDK欄は17.0.0でした。この経路はApp Store用のメタデータ書き換えをしません。

## 日常のビルドと更新

毎回の作業は `--check` とビルドだけです。Swift、SDK、上流インストーラーを再導入しないでください。Swiftや上流スクリプトのハッシュが変わると、補助スクリプトは互換性の再確認を求めて停止します。新しい版は、対応するXcode、互換修正、サンプルビルドを確認してから採用してください。

SDK登録後に初回構築が途中で止まった場合の再開と、よくあるエラーは [構築手順の復旧節](docs/setup.md#復旧と再利用)にあります。WSL内の削除だけではWindows上のVHDサイズが縮まらない場合があります。

## データとライセンス

AppleのSDK、Xcode.xip、IPA、署名鍵、アカウント情報は配布していません。Appleの配布物は本人が公式経路で取得し、適用される規約を確認してください。このガイドはAppleの規約や配布要件を変更しません。iCloud等への納品はビルドとは別の操作です。

本リポジトリの自作文書・補助スクリプトは [MIT License](LICENSE)。上流コードの転載・同梱はせず、固定commitを参照します。[omarchy-apple-devのライセンス](https://github.com/joshuaswarren/omarchy-apple-dev/blob/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942/LICENSE)と各依存・Apple配布物の条件はそれぞれ独立しています。

文書・自作補助スクリプトの作成支援: Codex（GPT-6.1 Sol、推論設定は未記録）。公開文書の校正: Gemini 3.8 Flash / High。
