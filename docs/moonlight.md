# Moonlight iOSをWindows/WSLでビルドする

日本語 | [English](moonlight.en.md)

Moonlight iOS 9.0.2のアプリ本体をWSLでコンパイルし、未署名IPAを作ります。Storyboard、アセット、Core Dataモデルと生成クラスは、GitHub ActionsのmacOSランナーで先に生成します。手元のMacは不要ですが、**この経路は完全ローカルではありません**。

対象は[Moonlightの固定commit](https://github.com/moonlight-stream/moonlight-ios/tree/02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a)です。汎用のXcodeプロジェクト変換ツールではありません。2026-10-08に、この版にアプリ内Tailscaleを追加したソースでIPA生成を確認しました。初回の成果物はSceneライフサイクル未対応によりiOS 27.0.1 / LiveContainer 3.8.0で起動時に停止しました。以下の手順にはScene対応パッチを含めています。修正版の実機動作は確認中です。このガイドにTailscale追加コードやIPAは含めていません。

## 準備

[環境構築](setup.md)に従い、WSLの通常ユーザーからSwift 6.4、iPhoneOS 27.0 SDK、固定版omarchy-apple-devを利用できる状態にします。既存の環境があれば再利用します。Python 3.12以降、Git、GitHub CLIも必要です。以下のコマンドはWSLで実行します。

```bash
git -c core.autocrlf=false clone --recursive \
  https://github.com/moonlight-stream/moonlight-ios.git "$HOME/moonlight-ios"
git -C "$HOME/moonlight-ios" checkout 02dc9780496eeeac6d01c8bbdccb8b6fe71ef28a
git -C "$HOME/moonlight-ios" submodule update --init --recursive
git clone https://github.com/hinatamaxxx/windows-ipa-build-guide.git \
  "$HOME/windows-ipa-build-guide"
```

作業はLinux側のファイルシステムで行い、改行はLFを保ちます。Windows側の変更済みソースをコピーする場合、未コミットの変更も含めてください。リソースの改行が変わるだけでもハッシュ照合は失敗します。

## リソースを生成する

このガイドを自分のGitHubアカウントへforkし、Actionsを有効にして「Moonlight resource kit」を手動実行します。ワークフローは公開されている未改変のMoonlightを固定commitから取得します。手元の変更済みソースやApple SDKはアップロードしません。GitHubの利用枠と料金を確認してください。

```bash
gh workflow run moonlight-resources.yml --repo YOUR_ACCOUNT/windows-ipa-build-guide
gh run list --repo YOUR_ACCOUNT/windows-ipa-build-guide \
  --workflow moonlight-resources.yml --limit 5
# 成功した実行のIDを指定する
gh run download RUN_ID --repo YOUR_ACCOUNT/windows-ipa-build-guide \
  --name moonlight-resource-kit-02dc978 --dir "$HOME/moonlight-kit-download"
mkdir -p "$HOME/moonlight-resource-kit"
tar -xzf "$HOME/moonlight-kit-download/moonlight-resource-kit.tar.gz" \
  -C "$HOME/moonlight-resource-kit"
```

リソースキットは30日間保存されます。期限後は再生成します。信頼できるforkの成功した実行から取得し、実行されたワークフローも確認してください。マニフェストのハッシュ照合は破損やソースの不一致を検出しますが、配布者の署名検証ではありません。

キットにはコンパイル済みの画面・アセット・モデル、Core Data生成コード、Info.plistの雛形、ライセンス、ハッシュ一覧が入ります。アプリの実行ファイルやApple SDKは含みません。確認時のリソース生成環境はXcode 26.6 / iPhoneOS 26.5 SDKでした。`macos-latest`は更新されるため、実際の版は各キットの`manifest.json`に記録します。

## アプリ本体をビルドする

まず固定版の上流ソースへScene対応パッチを適用します。iOS 27 SDKでビルドするアプリには[UIKitのSceneライフサイクル](https://developer.apple.com/documentation/technotes/tn3187-migrating-to-the-uikit-scene-based-life-cycle)が必要です。このパッチは既存のiPhone/iPad用Storyboardを再利用し、複数ウィンドウは有効にしません。既にScene対応を行った独自ソースへ二重に適用しないでください。

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

`--omarchy`は[固定commit](https://github.com/joshuaswarren/omarchy-apple-dev/tree/acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942)を展開した場所に合わせます。パーサーのハッシュが違う場合は停止します。独自のSDKやSwift配置には`--sdk-bundle`と`--swift-bin`を指定できます。

初回はOpenSSL 3.6.3000のXCFrameworkを取得し、固定SHA-256と照合します。iOS arm64用の動的FrameworkだけをIPAへ同梱します。キャッシュは`~/.cache/moonlight-ios-build`です。シミュレーター用のFrameworkは使いません。

ソースに`TailscaleBridge`がある場合は、その`build-apple.sh`と`go run ./cmd/notices`も実行します。この追加経路はGo 1.27.1で確認しました。ビルド対象のコードとスクリプトを確認してから実行してください。通常の上流ソースにはこのディレクトリはなく、Tailscaleは追加されません。

## 出力と確認範囲

日時付きディレクトリに未署名IPA、`verification.json`、`SHA256SUMS.txt`、`logs/`を生成します。既存の納品IPAは上書きしません。対象はarm64、最低iOS 15.0です。ビルドではリソースと元ソースのハッシュ、OpenSSLのハッシュ、IPAのZIP CRCを検査し、Mach-Oヘッダーと依存ライブラリをログへ記録します。

確認済みの成果物では、主実行ファイルとOpenSSLがiOS用であること、OpenSSLの参照先と同梱場所、実行権限も確認しました。IPAの生成成功は実機動作の証明ではありません。LiveContainerへの取り込み、署名処理、ログイン、映像・音声・操作は端末で別途確認してください。

画面・アセット・データモデルを変更すると既存キットは使えません。ワークフローの参照先と出力元を見直し、変更したリソースから生成し直します。公開ワークフローに非公開ソースや認証情報を追加しないでください。

## コンパイル時の注意

この補助スクリプトは、XcodeのSources一覧からObjective-C/CとSwiftをコンパイルし、Core Dataの生成コードもリンクします。SwiftのObjective-C公開ヘッダー生成には元のbridging headerを指定します。ヘッダー検索先を無制限に追加するとFFmpegの`time.h`がSDKを隠すため、必要なディレクトリだけを指定しています。OpenSSLの小文字`openssl/`参照にはキャッシュ内のシンボリックリンクを使います。SDK自体は書き換えません。

任意のXcode設定や追加のビルドフェーズを再現する機能はありません。ソース構成やライブラリを変更した場合は補助スクリプトを見直してください。失敗時は出力先の`logs/`から最初に失敗したコンパイルを確認します。

Moonlightと同梱する依存ライブラリには、それぞれのライセンスが適用されます。成果物を配布する場合は、対応するソースの提供を含めて各ライセンス条件を満たしてください。
