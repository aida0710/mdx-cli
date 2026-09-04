# mdx-cli v2.0.0 リリース設計

## 目的

TOTP 自動入力と単体バイナリ配布を、安全に移行・更新できる形で v2.0.0 として公開する。
既存の `uv tool install .` 利用者、Web/IPMI コンソール、checksum が取得できない場合、
更新途中の失敗を明示的に扱う。

## 対象

- TOTP シークレットの登録、検証、保存、自動入力、削除
- TOTP を SSO の TOTP フォーム送信直前に生成する仕組み
- `questionary` の raw mode が使えない端末向けの非対話登録
- `uv tool install .` から単体バイナリへの移行
- macOS、Linux、Windows 用インストーラ
- checksum 必須の配布と更新失敗時の復旧
- v2.0.0 のバージョン、テスト、リリースワークフロー、利用手順

## 認証設計

`sso_login()` の `otp` は固定文字列または引数なしの provider を受け取る。
固定文字列は既存呼び出しとの互換性を保ち、provider は TOTP フォームを検出した時点で一度だけ呼ぶ。
保存済みシークレットを使う `login` と自動再ログインは provider を渡し、30 秒境界をまたいだ古いコードを送らない。

対話登録では Base32 シークレットを非表示で受け取り、認証アプリに表示された現在のコードを
ユーザーから受け取ってローカル検証する。生成した OTP は標準出力へ表示しない。
検証は現在の時間窓と前後一窓を定時間比較し、入力遅延と小さな時計ずれを許容する。

`mdx auth otp --non-interactive` は標準入力の先頭行からシークレットを読む。
標準入力が TTY の場合は、画面へシークレットが表示される事故を防ぐため失敗させる。
これは、保存済み ID/PW がある一方で `questionary` の raw mode が使えない Web/IPMI コンソールから、
権限を制限したファイルまたは安全なパイプを使って登録する経路である。
`--delete --non-interactive` は明示的な削除指定として確認なしで削除する。

保存済みシークレットが壊れている場合はログイン全体をクラッシュさせず、OTP 手入力へ戻す。
ログアウトでは従来どおり ID/PW、TOTP、トークンを削除する。

## インストール設計

インストーラはバイナリと同じリリースの `checksums.txt` を必須とし、取得不能、対象行なし、
SHA-256 計算コマンドなし、不一致のいずれでもインストール前に終了する。

macOS/Linux では、既定の `~/.local/bin/mdx` が uv の tool entrypoint である場合、上書きせず
`uv tool uninstall mdx-cli` を先に実行するよう案内する。Windows でも uv の tool receipt を検出し、
PATH 上で旧 entrypoint が優先される状態を作らない。

Windows の更新では既存バイナリを `.old` へ移した後、新バイナリの配置に失敗した場合は
`.old` を元へ戻す。成功した場合だけバックアップを削除する。

## リリース設計

`pyproject.toml` と `mdx_cli.__version__` を 2.0.0 に揃える。
タグ `v2.0.0` と両バージョンの一致を検証し、テスト、Ruff、各OSのPyInstallerビルド、
生成バイナリの `--version` を通過した場合だけ GitHub Release を作成する。
Release には4バイナリ、`checksums.txt`、両インストーラを添付する。

## 移行

uv 版を継続するユーザーは `uv tool install . --force` を使える。
単体バイナリへ切り替えるユーザーは、先に `uv tool uninstall mdx-cli` を実行してから
インストーラを実行する。uv の環境と entrypoint だけが削除され、`~/.config/mdx-cli` の設定や
認証情報は維持される。

## 検証境界

単体テストで TOTP ベクタ、コード検証、遅延生成、破損シークレット、非対話登録、uv 検出、
checksum 必須化、文書と成果物名の整合性を確認する。ローカルでは利用可能なシェル構文検査、
PowerShell 構文検査、PyInstaller ビルドを行う。実 MDX の SSO と Web/IPMI 固有の termios 動作は、
資格情報を扱わずに自動検証できないため、リリース後の実機確認項目として残す。
