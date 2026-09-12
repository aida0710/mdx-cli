# はじめに

Webポータルで行っている操作を、いつものターミナルから。
mdx-cliは、mdx IのVM・プロジェクト・ネットワークを操作する非公式CLIツールです。

> **非公式ツールについて**
>
> mdx-cliはmdxの公式提供・サポート対象ツールではありません。このサイトはmdx-cliの利用手引きです。mdx自体の利用条件や仕様は[公式の利用手引き](https://docs.mdx.jp/ja/index.html)をご確認ください。

## 使い始める前に

- mdxのWebポータルを利用できるアカウントとプロジェクトを用意します。
- ログインは **MDX Local Authに対応**しています。学認経由のログインには対応していません。
- バイナリ版ならPythonの準備は不要です。[インストール手順](install.html)から始めてください。

## 最初の3コマンド

インストールが済んだら、ログインして操作対象を選びます。まずは既存VMの一覧を確認しましょう。

```bash
mdx auth login
mdx project select
mdx vm list
```

ログイン時はユーザー名・パスワード・ワンタイムパスワードを入力します。プロジェクトの選択は保存され、次回以降も使われます。

## ポータルの操作をCLIに置き換える

| やりたいこと | コマンド | 手順 |
| --- | --- | --- |
| 利用中のリソースを確認 | `mdx project summary` | [プロジェクト](projects.html) |
| ポイントの明細と合計残高を確認 | `mdx project points` | [プロジェクトと利用状況](projects.html) |
| 24時間の消費ポイントを確認 | `mdx project usage --hours 24` | [プロジェクトと利用状況](projects.html) |
| 資源・VM状態の概要を確認 | `mdx project overview` | [プロジェクトと利用状況](projects.html) |
| VMの一覧・詳細を見る | `mdx vm list` / `mdx vm show` | [VM操作](vm.html) |
| VMにSSH接続 | `mdx vm ssh my-vm-01` | [SSH接続](ssh.html) |
| テンプレートからVMを作成 | `mdx vm deploy` | [VM操作](vm.html) |
| セグメントを確認 | `mdx network segment list` | [ネットワーク](network.html) |
| ACL・DNATを管理 | `mdx network acl list` / `mdx network dnat list` | [ネットワーク](network.html) |
| 操作の進捗を確認 | `mdx task list` | [タスクと操作履歴](tasks.html) |

例の `my-vm-01` は、実際のVM名に置き換えてください。

## 次に進む

初回セットアップは[インストール](install.html) → [ログインと認証](auth.html) → [プロジェクトを選ぶ](projects.html)の順に進めます。準備済みの方は[VMを操作する](vm.html)を開いてください。
