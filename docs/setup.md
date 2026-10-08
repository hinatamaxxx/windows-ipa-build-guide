# 初回の環境構築

このページのコマンドは、Windows側とWSL内を区別して実行します。コミュニティのAUR/GitHubコードは、固定版の内容を読んでから実行してください。OS再インストール、ディスク消去、ファイアウォール変更は不要です。

## 1. WSL2とArch Linux

まずWindows PowerShellで既存の環境と容量を確認します。

```powershell
wsl --list --verbose
wsl --version
Get-PSDrive -PSProvider FileSystem
Get-CimInstance Win32_Processor | Select-Object Name,VirtualizationFirmwareEnabled
```

XIP、展開したSDK、SDK登録コピー、Swiftビルドキャッシュを合わせ、50GiB以上の空きがあると作業しやすくなります。検証環境では展開に12GiB級、登録コピーに13GiB級を使いました。プロジェクトの大きさによって追加容量が必要です。

WSLがなければ、管理者PowerShellから公式の方法で導入します。

```powershell
wsl --install --no-distribution
```

Windowsが再起動を求めた場合、作業を保存して本人が再起動します。次に公式Arch Linuxを取得します。既に同じディストリビューションがあればインストールを繰り返しません。

```powershell
wsl --install archlinux
wsl --list --verbose
```

参考: [Microsoft WSLの基本コマンド](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)、[Arch公式ダウンロード](https://archlinux.org/download/)。

## 2. 通常ユーザーと公式依存

Archがrootで起動する場合、通常ユーザーを作ります。以下の `builder` は任意のLinuxユーザー名に置き換えます。Windowsから `wsl -d archlinux --user root` を開き、WSL内で実行してください。パスワードは本人が入力します。

`sudo` / `visudo` が未導入の場合は、このrootセッションで先に `pacman -Syu sudo` を実行して公式パッケージを導入します。

```bash
useradd -m -G wheel -s /bin/bash builder
passwd builder
printf '%%wheel ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/90-wheel-password
chmod 0440 /etc/sudoers.d/90-wheel-password
visudo -cf /etc/sudoers
```

既存ユーザーやsudo設定がある場合は再作成しません。`/etc/wsl.conf` の既存内容を保ち、必要なセクションへ次を設定します。

```ini
[boot]
systemd=true

[user]
default=builder
```

Windows PowerShellでこのディストリビューションだけを終了し、通常ユーザーで開き直します。WSL内の未保存作業を先に保存してください。

```powershell
wsl --terminate archlinux
wsl -d archlinux -- id
```

以降のビルドは通常ユーザーです。WSL内で公式Arch依存を不足分だけ導入します。

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel git zip unzip libimobiledevice openssl \
  poppler libheif python pkgconf go patchelf libxml2-legacy libedit
```

## ガイド自身を取得する

この公開リポジトリのGitHub画面で **Code → HTTPS** のclone URLをコピーします。WSL内で以下を実行し、入力を求められたらそのURLを貼り付けます。既に取得済みなら、その実際のディレクトリを `GUIDE_DIR` に指定し、cloneは省略します。

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
read -r -p 'このガイドのHTTPS clone URL: ' GUIDE_URL
git clone "$GUIDE_URL" "$GUIDE_DIR"
```

ここで設定するシェル変数と後続の `export PATH` は、そのWSLセッションにだけ有効です。閉じた場合は必要な変数を設定し直します。日常ビルド用の補助スクリプトは必要なPATHを自身で設定するため、シェル設定の永続変更は必須ではありません。

## 3. Swift 6.4

検証したAUR recipeは `swift-bin` 6.4.0-2、commit `76ec647c95acf2d46b6f0b235660084d0bd69eb2`。公式Swift tarballをrecipeで包装したものですが、AUR recipe自体はコミュニティコードです。内容、source、ハッシュを確認してから通常ユーザーで作成します。

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

Swift公式tarballの検証済みSHA-256は `50863678e3bafd91fcbc94c0bb76610bab37c1ee01e335fc7d8616904e03e19a`。recipeがこの入力を確認することを読み取ってください。通常ビルドにyayは不要です。検証環境ではyay 13.0.1も導入しましたが、この手順ではAURの固定recipeを直接使います。

## 4. 固定版の上流とSwiftBuild修正

WindowsのCRLFを避けるため、WSL内で上流をcloneします。既存ディレクトリは上書きせず、同じcommitなら再利用します。

```bash
OMARCHY_COMMIT=acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942
OMARCHY_DIR="$HOME/omarchy-apple-dev-acd373c"
git clone https://github.com/joshuaswarren/omarchy-apple-dev.git "$OMARCHY_DIR"
git -C "$OMARCHY_DIR" checkout --detach "$OMARCHY_COMMIT"
git -C "$OMARCHY_DIR" rev-parse HEAD
less "$OMARCHY_DIR/install-toolchain.sh"
```

Swift 6.4のroot所有xcspecへの書き込みが、上流の `--user-only` でも発生します。自作スクリプトは既知の元ハッシュを確認し、次の3ファイル・4値だけを変更します。既に修正済みなら変更しません。異なる内容なら停止します。

| `/usr/lib/swift/usr/share/pm/` 以下のファイル | 修正 |
|---|---|
| `SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec` | 入力エンコード `$(InputFileTextEncoding)` → `utf-8`（1箇所） |
| `SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec` | 出力エンコード `UTF-16` → `binary`（2箇所） |
| `SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec` | 出力エンコード `UTF-16` → `binary`（1箇所） |

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --check
# 変更計画を読んでから実行。新規のバックアップ先を指定する。
sudo python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --apply \
  --backup "$HOME/SwiftBuild-originals-$(date -u +%Y%m%dT%H%M%SZ)"

# 上流の元ファイルを残し、修正済みxcspecを再書き込みしない派生版をローカル生成
python3 "$GUIDE_DIR/scripts/prepare_installer.py" --repo "$OMARCHY_DIR"
```

派生版は `$OMARCHY_DIR/install-toolchain-wsl-guarded.sh` に出力されます。元の `install-toolchain.sh` は保持されます。変更は、修正済みxcspecの再書き込みを内容一致の確認に置き換える1文だけです。

root実行はこの3ファイルの修正と公式依存の導入だけです。通常ユーザーの書き込み権限拡大や、インストーラー全体のroot実行は不要です。バックアップは削除せず保持してください。

## 5. Apple公式XcodeとSDK取り込み

本人が [Apple Developer Downloads](https://developer.apple.com/download/all/?q=Xcode) からSwift 6.4に対応するXcode 27.xipを取得します。ログイン、規約確認、取得資格の確認は本人が行います。第三者配布のSDKを使わず、XIPや展開したSDKをこのリポジトリへ追加しないでください。

検証したXcode_27.xipは2,014,229,334 bytes、SHA-256 `6a270c53a5a0c5e0ac78125342d44c3cfff2716ec390373cd5e30834d80a67c3`。別の版にはこの値を使いません。この検証は取得元とファイル内容の整合確認であり、AppleのXIP署名を独立に検証したものではありません。

Windowsに置いたXIPの実パスを、WSL内の `wslpath -u 'C:\path\to\Xcode_27.xip'` で変換します。WSL内で次を実行します。

```bash
export PATH="/usr/lib/swift/usr/bin:$HOME/.local/bin:$PATH"
sha256sum '/mnt/c/path/to/Xcode_27.xip'
# 公式取得元、対象版、上記ハッシュの一致を確認してから取り込む
XCODE_XIP='/mnt/c/path/to/Xcode_27.xip' \
  bash "$OMARCHY_DIR/install-toolchain-wsl-guarded.sh" --user-only
swift sdk list
```

`darwin` が登録され、`$HOME/.swiftpm/swift-sdks/darwin.artifactbundle` にSDKが生成されます。固定版インストーラーがxtool、rcodesign、ipsw、pymobiledevice3、SDK内のactool等とOpenAppleMacrosServerを準備します。SDKを再展開する時間と容量がかかるため、途中で止まってもまず登録済み状態を確認します。

pymobiledevice3は上流で未固定のpip導入です。当時の版は11.24.0でした。厳密に同じ版を使う場合は、初期構築後に既存venv内だけで `"$HOME/pymobile3-venv/bin/python" -m pip install 'pymobiledevice3==11.24.0'` と指定します。このガイドでは端末・アカウント操作に使いません。

## 6. サンプルIPAと日常ビルド

空いているディレクトリで、認証セットアップを行わずサンプルを生成します。

```bash
cd "$HOME"
"$HOME/.local/bin/xtool" new HelloOmarchy --skip-setup
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

新しい出力ディレクトリに未署名IPA、検証JSON、ログができれば、ローカル生成の確認は完了です。別の対応プロジェクトでは `--project` を変更します。上流を別の場所へ置いた場合は `--repo "$OMARCHY_DIR"` を指定します。SDKとSwiftの初期導入は毎回行いません。

## 復旧と再利用

- `PermissionError` がxcspecで出る: 上記3ファイルの元/修正後ハッシュを確認し、バックアップ付き互換修正と派生インストーラーを使います。rootでインストーラー全体を実行しないでください。
- SDK登録済みで残るツール構築が失敗: `swift sdk list` とSDKの存在を確認し、通常の `--user-only` 経路で失敗段階を再開します。`--repair` はSDK登録を外してやり直す経路なので、通常の再開では使いません。
- OpenAppleMacrosServerだけ未完了: 固定ソースを通常ユーザーで `swift build -c release --build-system native --static-swift-stdlib --product OpenAppleMacrosServer --jobs 4` で再開できます。上流 `install_oam` の配置手順を確認し、SDK内の元サーバーをバックアップしてから成果物を置きます。署名鍵や端末設定は不要です。
- SDKを変えた後だけビルド失敗: 古いモジュールキャッシュの影響を切り分けるため、ソースの新規コピーでビルドします。プロジェクト全体を削除しないでください。
- `--check` のハッシュ不一致: 固定版と現在の版が異なります。原因を確認せず検証を外したり、古い互換パッチを強制適用しないでください。
- LLDBのlibpython3.12不足: 検証サンプルのIPA生成には影響しませんでした。デバッグを別途使うときに対応する依存を確認します。

環境を使わなくなった場合、WSLディストリビューションの削除はLinux側のファイルをすべて消します。`wsl --unregister` を実行する前に本人が必要なソース・成果物・バックアップを退避してください。このガイドは自動削除を行いません。
