# ドキュメントの編集・プレビュー

`content/*.md` が本文、`assets/` が配色・レイアウト・操作の実装です。
ページ構成は `scripts/build_docs.py` の `GROUPS` で管理します。
生成物は `_site/` に出力されます。READMEからの自動同期は行わないため、CLIの変更時は該当ガイドも更新してください。

## ローカルプレビュー

リポジトリの既存 `.venv` にある markdown-it-py を使います。追加インストールは不要です。

```sh
.venv/bin/python scripts/build_docs.py
.venv/bin/python -m http.server 8765 --bind 127.0.0.1 --directory pages/_site
```

ブラウザーで http://127.0.0.1:8765 を開きます。本文・スタイルを変更したら再ビルドしてリロードしてください。

## GitHub Pages

ビルド用の依存は `requirements.txt` に固定しています。GitHub Actions上でのみインストールします。
公開する際はGitHubの Settings → Pages → Source を GitHub Actions に設定し、mainブランチの `Documentation Pages` ワークフローを手動実行します。
pull requestではビルドだけ行います。pushによる自動公開は設定していません。
公開ディレクトリは `pages/_site` のみで、開発用ドキュメントやリポジトリのファイルは含みません。
