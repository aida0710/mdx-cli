# プロジェクトを選ぶ

```bash
mdx project list       # プロジェクト一覧
mdx project summary    # VM数・リソース・ストレージ使用量
mdx project select     # 使用するプロジェクトを選択（以降 --project-id 不要）
mdx project show <id>  # プロジェクト詳細
mdx project storage <id>  # ストレージ情報
mdx project keys <id>  # アクセスキー一覧
```

`project summary` の表示例:

```
VM（スポット）:
  稼働中: 5  停止: 2  未割当: 13  合計: 20

VMディスク:
  使用: 1,500 GB / 5,000 GB（残り 3,500 GB）

高速ストレージ: /fast/0/d12345678
  使用: 100.0 GB / 500.0 GB（残り 400.0 GB, 20.0%）

大容量ストレージ: /large/0/d12345678
  使用: 2,048.0 GB / 10,000.0 GB（残り 7,952.0 GB, 20.5%）

オブジェクトストレージ: /object
  使用: 512.0 GB / 5,000.0 GB（残り 4,488.0 GB, 10.2%）
```
