# VMにSSH接続する

VM名を指定して接続します。IPアドレスとログインユーザー名はVM情報から取得されます。

## 名前で接続する

```bash
mdx vm ssh my-vm-01
```

名前を省略すると、稼働中VMの一覧から選択できます。

```bash
mdx vm ssh
```

## 秘密鍵・ユーザー名を指定する

```bash
mdx vm ssh my-vm-01 -i ~/.ssh/mdx-key
mdx vm ssh my-vm-01 -u mdxuser
```

ユーザー名はテンプレートの `login_username` から自動検出します。VM側で変更している場合は `-u` で指定してください。

## グローバルIPを使う

```bash
mdx vm ssh my-vm-01 -g
```

通常はプライベートIPを使います。`-g` は接続先のIPを切り替える指定です。SSH接続には、選んだIPへのネットワーク経路と、VM側でSSHを受け付ける設定が必要です。

## 接続できないとき

`mdx vm show my-vm-01` で状態とIPを確認してください。起動状態・ネットワーク経路・ACL・VM側のSSH設定・秘密鍵を順に確認します。詳しくは[トラブルシューティング](troubleshooting.html)へ。
