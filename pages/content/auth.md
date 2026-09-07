# ログインと認証

Shibboleth SSO 経由でログインします。ユーザー名・パスワード・TOTP の入力が必要です。

```bash
mdx auth login     # ログイン（暗号化ファイルへ保存）
mdx auth login --keychain  # OSの資格情報ストアを使う場合だけ明示
mdx auth otp       # TOTPシークレットを登録（OTP自動入力）
mdx auth status    # 認証状態を確認
mdx auth logout    # ログアウト（全クレデンシャル削除）
```

- ユーザー名とパスワードはデフォルトで `~/.config/mdx-cli/credentials.enc` に暗号化して保存
- OSの資格情報ストア（macOS Keychain 等）を使う場合は `mdx auth login --keychain` を指定
  （`--keyring` も同じ意味です）。デフォルト経路ではKeychainへ接続しません
- 旧バージョンがKeychainへ保存した情報を明示的に削除してログアウトする場合は
  `mdx auth logout --keychain` を使います
- 2回目以降のログインは保存済みユーザーをそのまま使い、OTP の入力のみ
  （別ユーザーに切り替える場合は `mdx auth logout` してから `mdx auth login`）
- トークン期限切れ時は自動で再ログイン（TOTP登録済みなら入力不要、未登録ならOTPだけプロンプト）

### OTP の自動入力

ログイン後に `mdx auth otp` で認証アプリと同じ TOTP シークレット（Base32）を登録すると、
ログイン・再ログイン時の OTP 入力が不要になります。

```bash
mdx auth login          # 先にログイン（シークレットはこのアカウントに紐付く）
mdx auth otp            # 未登録なら登録、登録済みなら「登録し直す / 削除する」を選択
mdx auth otp --delete   # 登録を解除して手入力に戻す（確認あり）
```

シークレット入力は非表示です。続いて認証アプリ側の現在のOTPを入力し、ローカルで一致を確認します。
CLIが生成したOTPは画面やログへ出しません。

Web/IPMIコンソールなどで `questionary` のraw modeが使えない場合は、権限を制限したファイルまたは
安全なパイプからシークレットを渡せます。標準入力がTTYの場合は、シークレットの画面表示を防ぐため拒否します。

```bash
mdx auth otp --non-interactive < /path/to/totp-secret
```

入力はBase32シークレット1行です。登録後、`mdx auth login` で自動生成OTPが通ることを確認してください。
非対話で削除する場合は `mdx auth otp --delete --non-interactive` を使います。

- シークレットは登録時のユーザー名とセットで保存され、そのアカウントのログイン時だけ使われます
  （別ユーザーでログインする場合は自動入力されず、OTP の手入力に戻ります）
- 保存先は ID/PW と同じ場所で、`mdx auth logout` でまとめて削除されます
- 同じ端末にパスワードと第2要素が揃うことになるため、共有端末では登録しないでください
