# 初回の環境構築

日本語 | [English](setup.en.md)

このページのコマンドは、Windows側で実行するものとWSL内で実行するものを区別して書いています。コミュニティのAURやGitHubのコードは、固定版の内容を読んでから実行してください。OSの再インストール、ディスクの消去、ファイアウォールの変更は不要です。

## 1. WSL2とArch Linux

まずWindows PowerShellで、既存の環境と空き容量を確認します。

```powershell
wsl --list --verbose
wsl --version
Get-PSDrive -PSProvider FileSystem
Get-CimInstance Win32_Processor | Select-Object Name,VirtualizationFirmwareEnabled
```

XIP、展開したSDK、SDKの登録コピー、Swiftのビルドキャッシュを合わせて、50GiB以上の空きがあると作業しやすくなります。検証環境では、展開に12GiB前後、登録コピーに13GiB前後を使いました。プロジェクトの大きさによっては、さらに容量が必要です。

WSLがなければ、管理者PowerShellから公式の方法で導入します。

```powershell
wsl --install --no-distribution
```

Windowsが再起動を求めた場合は、作業を保存してから本人が再起動します。既にWSLがある場合は、先に `wsl --update` で更新してください。古いWSLでは、次の `wsl --install archlinux` で配布一覧にArchが出てきません。

次に公式のArch Linuxを取得します。同じディストリビューションが既にあれば、インストールを繰り返しません。

```powershell
wsl --update
wsl --install archlinux
wsl --list --verbose
```

WSLが使えるメモリは、既定では物理メモリの半分です。検証機は約31GiBのRAMを積んでいました。メモリの少ないPCでxtoolなどのビルドが途中で強制終了する場合は、Windowsの `%UserProfile%\.wslconfig` にスワップを足すか、メモリの上限を上げます。値はPCに合わせて決め、変更後は `wsl --shutdown` でWSLを再起動します。

```ini
[wsl2]
swap=16GB
```

参考: [Microsoft WSLの基本コマンド](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)、[WSLの詳細設定](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)、[Arch公式ダウンロード](https://archlinux.org/download/)。

## 2. 通常ユーザーと公式依存

Archがrootで起動する場合は、通常ユーザーを作ります。以下の `builder` は、任意のLinuxユーザー名に置き換えます。Windowsから `wsl -d archlinux --user root` を開き、WSL内で実行してください。パスワードは本人が入力します。

WSL版のArchには、`sudo` やテキストエディターが入っていないことがあります。その場合は、このrootセッションで先に `pacman -Syu sudo nano` を実行し、公式パッケージから導入します。

```bash
useradd -m -G wheel -s /bin/bash builder
passwd builder
printf '%%wheel ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/90-wheel-password
chmod 0440 /etc/sudoers.d/90-wheel-password
visudo -cf /etc/sudoers
```

既存のユーザーやsudo設定がある場合は、作り直しません。続けて `nano /etc/wsl.conf` で設定ファイルを開きます。既存の内容は残したまま、該当するセクションに次の2項目を設定してください。

```ini
[boot]
systemd=true

[user]
default=builder
```

Windows PowerShellでこのディストリビューションだけを終了し、通常ユーザーで開き直します。WSL内の未保存の作業は、先に保存してください。

```powershell
wsl --terminate archlinux
wsl -d archlinux -- id
```

以降のビルドは通常ユーザーで行います。WSL内で、不足している公式のArch依存だけを導入します。

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel git zip unzip less libimobiledevice openssl \
  poppler libheif python pkgconf go patchelf libxml2-legacy libedit librsvg
```

## 3. ガイド自身の取得

この公開リポジトリのGitHub画面で、**Code → HTTPS** のclone URLをコピーします。WSL内で以下を実行し、入力を求められたらそのURLを貼り付けます。既に取得済みなら、cloneは省略し、取得したディレクトリを `GUIDE_DIR` に指定します。

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
read -r -p 'このガイドのHTTPS clone URL: ' GUIDE_URL
git clone "$GUIDE_URL" "$GUIDE_DIR"
```

ここで設定するシェル変数と、後で出てくる `export PATH` は、そのWSLセッションの中でだけ有効です。そのため、以降の各節の冒頭で必要な変数を設定し直しています。日常ビルド用の補助スクリプトは必要なPATHを自分で設定するので、シェル設定を永続的に変更する必要はありません。

## 4. Swift 6.4

検証したAURのrecipeは、`swift-bin` 6.4.0-2のcommit `76ec647c95acf2d46b6f0b235660084d0bd69eb2` です。公式のSwift tarballを包装したものですが、recipe自体はコミュニティのコードです。内容、source、ハッシュを確認してから、通常ユーザーでパッケージを作成します。

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

検証したSwift公式tarballのSHA-256は `50863678e3bafd91fcbc94c0bb76610bab37c1ee01e335fc7d8616904e03e19a` です。recipeがこのハッシュで入力を確かめていることを、PKGBUILDで読み取ってください。通常のビルドにyayは不要です。検証環境ではyay 13.0.1も導入しましたが、この手順ではAURの固定recipeを直接使います。

## 5. 固定版の上流とSwiftBuild修正

WindowsのCRLF改行が混ざらないように、上流はWSL内でcloneします。既存のディレクトリは上書きせず、同じcommitなら再利用します。

```bash
OMARCHY_COMMIT=acd373c72e3500c66c5fdcd2ab0bcbda6e6f6942
OMARCHY_DIR="$HOME/omarchy-apple-dev-acd373c"
git clone https://github.com/joshuaswarren/omarchy-apple-dev.git "$OMARCHY_DIR"
git -C "$OMARCHY_DIR" checkout --detach "$OMARCHY_COMMIT"
git -C "$OMARCHY_DIR" rev-parse HEAD
less "$OMARCHY_DIR/install-toolchain.sh"
```

Swift 6.4では、上流のインストーラーを `--user-only` で実行しても、root所有のxcspecへ書き込もうとします。自作スクリプトは既知の元のハッシュを確かめてから、次の3ファイルの4つの値だけを変更します。既に修正済みなら変更せず、異なる内容なら停止します。

| `/usr/lib/swift/usr/share/pm/` 以下のファイル | 修正 |
|---|---|
| `SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec` | 入力エンコード `$(InputFileTextEncoding)` → `utf-8`（1箇所） |
| `SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec` | 出力エンコード `UTF-16` → `binary`（2箇所） |
| `SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec` | 出力エンコード `UTF-16` → `binary`（1箇所） |

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --check
# 変更計画を読んでから実行する。バックアップ先には、まだ存在しないディレクトリを指定する。
sudo python3 "$GUIDE_DIR/scripts/patch_swiftbuild.py" --apply \
  --backup "$HOME/SwiftBuild-originals-$(date -u +%Y%m%dT%H%M%SZ)"

# 上流の元ファイルを残したまま、修正済みxcspecを再び書き込まない派生版をローカルに生成する
python3 "$GUIDE_DIR/scripts/prepare_installer.py" --repo "$OMARCHY_DIR"
```

派生版は `$OMARCHY_DIR/install-toolchain-wsl-guarded.sh` に出力され、元の `install-toolchain.sh` はそのまま残ります。派生版で変わるのは1文だけです。修正済みxcspecを書き込む処理を、内容が一致するかの確認に置き換えています。

rootで実行するのは、この3ファイルの修正と公式依存の導入だけです。通常ユーザーの書き込み権限を広げたり、インストーラー全体をrootで実行したりする必要はありません。バックアップは削除せずに保持してください。バックアップはsudoで作るためroot所有になり、通常ユーザーでは削除できません。

## 6. Apple公式XcodeとSDKの取り込み

[Apple Developer Downloads](https://developer.apple.com/download/all/?q=Xcode) から、本人がSwift 6.4に対応するXcode 27.xipを取得します。ログイン、規約の確認、取得資格の確認は本人が行います。第三者が配布するSDKは使わず、XIPや展開したSDKをこのリポジトリへ追加しないでください。

検証したXcode_27.xipは2,014,229,334バイトで、SHA-256は `6a270c53a5a0c5e0ac78125342d44c3cfff2716ec390373cd5e30834d80a67c3` です。別の版にはこの値を使いません。この照合で確かめられるのは、取得元とファイルの内容が一致することだけです。AppleによるXIPの署名を独立に検証したものではありません。

Windowsに置いたXIPの実際のパスは、WSL内で `wslpath -u 'C:\path\to\Xcode_27.xip'` を実行してWSLのパスに変換します。続けてWSL内で次を実行します。

```bash
OMARCHY_DIR="$HOME/omarchy-apple-dev-acd373c"
export PATH="/usr/lib/swift/usr/bin:$HOME/.local/bin:$PATH"
sha256sum '/mnt/c/path/to/Xcode_27.xip'
# 公式の取得元、対象の版、上記のハッシュが一致することを確かめてから取り込む
XCODE_XIP='/mnt/c/path/to/Xcode_27.xip' \
  bash "$OMARCHY_DIR/install-toolchain-wsl-guarded.sh" --user-only
swift sdk list
```

成功すると `darwin` が登録され、`$HOME/.swiftpm/swift-sdks/darwin.artifactbundle` にSDKが生成されます。固定版のインストーラーは、xtool、rcodesign、ipsw、pymobiledevice3、SDK内のactoolなどと、OpenAppleMacrosServerを準備します。上流のコメントによると、初回はxtoolのビルドに約7分、OpenAppleMacrosServerのビルドに約5分かかり、これとは別にSDKの展開にも時間がかかります。SDKの再展開には時間と容量がかかるため、途中で止まった場合も、まず登録済みかどうかを確認します。

pymobiledevice3は、上流では版を固定せずにpipで導入されます。検証時の版は11.24.0でした。厳密に同じ版を使う場合は、初期構築の後に既存のvenvの中だけで `"$HOME/pymobile3-venv/bin/python" -m pip install 'pymobiledevice3==11.24.0'` と指定します。このガイドでは、pymobiledevice3を端末やアカウントの操作には使いません。

## 7. サンプルIPAと日常ビルド

空いているディレクトリで、認証のセットアップを行わずにサンプルを生成します。

```bash
GUIDE_DIR="$HOME/windows-ipa-build-guide"
cd "$HOME"
"$HOME/.local/bin/xtool" new HelloOmarchy --skip-setup
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" --check
python3 "$GUIDE_DIR/scripts/build_ipa.py" --project "$HOME/HelloOmarchy" \
  --output-dir "$HOME/ipa-deliveries" --bundle-id com.example.HelloOmarchy
```

新しい出力ディレクトリに未署名IPA、検証JSON、ログができれば、ローカル生成の確認は完了です。別の対応プロジェクトをビルドするときは、`--project` を変更します。上流を別の場所に置いた場合は、`--repo "$OMARCHY_DIR"` を指定します。SDKとSwiftの初期導入は毎回行いません。

### SVGアイコンとSDK番号

SVGを含む画像カタログの変換には `rsvg-convert` が必要です。上記の `librsvg` パッケージに含まれます。`Failed to rasterise SVG asset` と `rsvg-convert: No such file or directory` が出た場合は、WSL内で `sudo pacman -S --needed librsvg` を実行し、`rsvg-convert --version` を確認してから通常ユーザーでビルドし直してください。

この環境では、iPhoneOS 27.0 SDKを使っても、生成された実行ファイルのSDK欄が最低OSと同じ17.0になる場合があります。検証JSONの `source_sdk_version` と `macho_sdk_version` を確認してください。SDKに応じた新しい画面表示を使うアプリでは、この違いにも注意が必要です。

最低OSが17.0、使用するSDKが27.0のSwiftPMターゲットでは、次のリンク設定で実行ファイルのSDK欄が27.0になることを確認しています。SDKの実物に合わせた指定であり、端末の動作確認に代わるものではありません。SDKを更新した場合は値を見直してください。

```swift
linkerSettings: [.unsafeFlags([
    "-Xlinker", "-platform_version", "-Xlinker", "ios",
    "-Xlinker", "17.0", "-Xlinker", "27.0"
])]
```

## 復旧と再利用

- xcspecで `PermissionError` が出る場合は、上記3ファイルの元と修正後のハッシュを確認し、バックアップ付きの互換修正と派生インストーラーを使います。インストーラー全体をrootで実行しないでください。
- SDKの登録後に残りのツール構築が失敗した場合は、`swift sdk list` とSDKの存在を確認し、通常の `--user-only` の経路で失敗した段階から再開します。`--repair` はSDKの登録を外してやり直す経路なので、通常の再開には使いません。
- OpenAppleMacrosServerだけが未完了の場合は、固定版のソースを通常ユーザーで `swift build -c release --build-system native --static-swift-stdlib --product OpenAppleMacrosServer --jobs 4` としてビルドし直せます。上流の `install_oam` の配置手順を確認し、SDK内の元のサーバーをバックアップしてから成果物を置きます。署名鍵や端末の設定は不要です。
- SDKを変えた後にだけビルドが失敗する場合は、古いモジュールキャッシュが原因かを切り分けるため、ソースの新しいコピーでビルドします。プロジェクト全体は削除しないでください。
- `--check` でハッシュが一致しない場合は、固定版と現在の版が異なっています。原因を確認しないまま検証を外したり、古い互換パッチを強制的に適用したりしないでください。
- `--check` が `pymobile3-venv cannot import cryptography` で止まる場合は、`pacman -Syu` でPythonの版が上がった可能性があります。`python3 -m venv --clear "$HOME/pymobile3-venv"` でvenvを作り直し、`"$HOME/pymobile3-venv/bin/pip" install 'pymobiledevice3==11.24.0'` で入れ直してください。
- `--check` でSwiftの版やSwiftBuild修正のハッシュが合わなくなった場合は、swift-binを入れ直したか、依存ライブラリの更新で影響を受けた可能性があります。互換性を確かめるまでは、`/etc/pacman.conf` の `IgnorePkg` で該当パッケージの更新を止めることもできます。
- `ship.sh` が `unresolved $(...) placeholders` で止まる場合は、Info.plistに `$(AppIdentifierPrefix)` などのチームIDの置き換えが残っています。補助スクリプトはチームIDを渡さないため、この状態のプロジェクトはこの経路ではビルドできません。
- 補助スクリプトが `Several apps under xtool/` で止まる場合は、`xtool/` に古い `.app` が残っています。不要な `.app` を `xtool/` の外へ移してからビルドし直します。
- LLDBで `libpython3.12` が不足する件は、検証したサンプルのIPA生成には影響しませんでした。デバッグを別に使うときに、対応する依存を確認します。

環境を使わなくなった場合、WSLのディストリビューションを削除するとLinux側のファイルはすべて消えます。`wsl --unregister` を実行する前に、必要なソース、成果物、バックアップを本人が退避してください。このガイドは自動では何も削除しません。
