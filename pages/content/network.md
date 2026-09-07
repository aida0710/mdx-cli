# ネットワーク・ACL・DNAT

### セグメント・IP

```bash
mdx network segment list         # セグメント一覧
mdx network segment show         # セグメント詳細（一覧から選択可能）
mdx network ips                  # 割当可能グローバルIP一覧
mdx network check-ip             # グローバルIPv4 使用状況チェック（穴DNATは確認後に削除可）
mdx network check-ip --fix       # 確認なしで穴DNATを即削除
mdx network check-acl            # 死んだVM宛のACL（穴）を検出（確認後に削除可）
mdx network check-acl --fix      # 確認なしで穴ACLを即削除
```

`check-ip` の表示例:

```
グローバルIPv4 使用状況:

  203.0.113.10  DNAT → 10.0.0.20 (db-server)
  203.0.113.11  VM: web-server
  203.0.113.12  VM: my-vm-01
  203.0.113.13  未使用
  203.0.113.14  未使用

  合計: 5  使用中: 3  未使用: 2
```

VM直接割当・DNAT経由・未使用を一覧表示。DNATの宛先からVM名も逆引き表示。並列取得で高速。

`check-acl` はプロジェクト全体のACLを走査し、宛先（`10.15.*`）が現存しないVMを指すルールを「穴」として検出する。VMを削除してもACL/DNATは残るため、IPが再割当されると意図しない通信を許可してしまう。

`check-ip` / `check-acl` は穴を検出すると「削除しますか?」と確認し、yes で一括削除する。`--fix` を付けると確認なしで即削除する。VM詳細の取得に一部失敗した場合は、穴判定が不正確になるため削除をスキップする（誤削除防止）。

### DNAT（全て対話式）

```bash
mdx network dnat list    # DNAT一覧
mdx network dnat add     # 追加（グローバルIP一覧から選択、宛先を入力）
mdx network dnat edit    # 編集（一覧から選択、現在値をデフォルト表示）
mdx network dnat delete  # 削除（一覧から選択可能）
```

### ACL（全て対話式）

```bash
mdx network acl list     # ACL一覧（セグメント自動選択）
mdx network acl add      # 追加（プロトコル・アドレス・ポートを対話入力）
mdx network acl edit     # 編集（一覧から選択、現在値をデフォルト表示）
mdx network acl delete   # 削除（一覧から選択可能）
```
