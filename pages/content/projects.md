# プロジェクトと利用状況

## プロジェクトを選ぶ・情報を見る

```bash
mdx project list       # テナント・所属プロジェクト一覧
mdx project summary    # VM数・リソース・ストレージ使用量
mdx project select     # 使用するプロジェクトを選択（以降 --project-id 不要）
mdx project show       # ID・名称・種別・申請者・利用期間（show <id> も使用可）
mdx project resources  # CPU/GPU要求量・使用量・割当量・翌月割当量・Rminなど
mdx project users      # ユーザー一覧（全ページ取得）
mdx project points     # 合計残高・購入・利用・残ポイントと利用期限
mdx project usage      # 最近7日間の資源使用量・消費ポイント
mdx project usage --hours 24  # 直近の正時（JST）までの24時間
mdx project overview   # ダッシュボードの資源概要・一覧・VM状態別件数
mdx project storage <id>  # ストレージ情報
mdx project keys <id>  # アクセスキー一覧
```

`show`・`resources`・`users`・`points`・`usage`・`overview` は `--project-id <id>` / `-p <id>`、
環境変数 `MDX_PROJECT_ID`、選択済みプロジェクトの順で対象を解決します。
`show <id>` の明示引数も環境変数・選択済み設定より優先します。
いずれも `--json` でJSON出力に切り替えられます。
`list --json` はテナントの `name` と `projects[]` の階層を保持し、通常表示では所属先とプロジェクトを一覧にします。
`show` はプロジェクト情報API、`summary` は従来どおりVM数と資源・ストレージ使用量の集約です。

## ユーザー一覧

ユーザー一覧は既定で1リクエスト100件ずつ全ページを取得します。
`--page` を指定すると、そのページのみを取得します。`--page-size` は1〜100です。
JSONは `count` と `results` を含み、単一ページ取得時はAPIの総件数とページ情報も保持します。
全ページ取得時の `count` は取得したユーザー数です。

```bash
mdx project users --page 1 --page-size 10
mdx project users --ordering=-username --username 'alice' --email 'example.jp' --auth '学認' --json
```

`auth` は認証方式（例: `学認`・`mdx認証基盤`）です。
フィルター値はそのままAPIへ渡します。完全一致・部分一致の扱いは未確認です。

## ポイントと合計残高

```bash
mdx project points
mdx project points --json
```

`points` はページ条件を付けず全件を取得し、最終消費処理日時 `lastConsumed` と各ポイントの値を保持します。
通常表示では明細とは別に **合計残高** を表示します。合計は全明細の `remaining_points` をDecimalで加算した値で、
期限による除外は行いません。JSONには文字列の `total_remaining_points` を追加します。
残ポイントに欠損・数値以外の値があれば部分合計は表示せず、合計は「算出できません」（JSONでは `null`）になります。

## 資源使用量・消費ポイント

資源利用レポートは閲覧用のPOSTで取得します。
`--days` は7・30・90・365に対応し、省略時は7日です。任意期間は `--start` と `--end` の両方を指定します。
日時は厳密な `YYYY-MM-DD HH`（00〜23時）で、終了を開始より後にしてください。`--days` との併用はできません。
日時をタイムゾーン変換せず送信します。サーバー側のタイムゾーンと期間端点の包含関係は未確認です。

### 24時間の消費ポイント

時間数で指定する場合は `--hours 24` を使います。JSTの現在時刻を正時へ切り捨て、その24時間前からの
期間を任意期間APIへ送ります。たとえばJSTで9月12日14:37に実行すると、9月11日14:00〜9月12日14:00です。
分単位で「現在まで」の指定はできません。通常表示に対象期間を表示し、JSONには `period`
（`start`・`end`・`hours`・`timezone: "JST"`）を追加します。
`--hours` は1以上で、`--days`・`--start`・`--end` と併用できません。

```bash
mdx project usage --days 30
mdx project usage --hours 24
mdx project usage --hours 48 --json
mdx project usage --start '2026-09-05 00' --end '2026-09-12 00'
mdx project usage --days 90 --lang en --json
mdx project usage --html > usage.html
mdx project usage --days 365 --output usage.html
```

### レポートの出力形式

`--lang` は `jp`（既定）または `en`。通常出力ではレポート内の表を表示し、`--json` は元レスポンスの
`html`・`err_msg` などに、抽出した `tables` を追加します。
各表は `caption`・`headers`・`rows` を持ち、`rowspan` / `colspan` は値を複製して矩形の行配列に展開します。
複数段の見出しは ` / ` で結合し、見出しのない表は `headers: []` とします。
数値も単位・桁区切り・小数桁を保った文字列なので、機械処理時は必要な列を選んで変換してください。合計行も `rows` に含みます。
`--html` は元HTMLを標準出力へ、`--output` / `-o` はUTF-8ファイルへ保存します。
`--json`・`--html`・`--output` はいずれか1つのみ指定できます。
APIの `err_msg` や空HTMLは終了コード1となります。表がない場合も通常表示はエラーですが、HTMLとJSON出力で内容を確認できます。

## ダッシュボードの概要

```bash
mdx project overview
```

`overview --kind` は `resource`・`resource_list`・`vm`・`spot_vm`・`guarantee_vm`・`all`（既定）に対応します。
単一種別のJSONはそのAPIのレスポンス、`all` のJSONは各種別をキーにしたオブジェクトです。
通常表示では資源概要・割当資源・専有VM・スポットVM・起動保証VMに分け、入れ子の値を項目ごとの行へ展開します。
既知の項目名は日本語で表示し、未知の項目も省略せず表示します。JSON出力の構造は従来どおりです。

```bash
mdx project overview --kind resource_list --json
mdx project overview --kind vm --json
```

## APIとの対応・確認範囲

これらは提示されたポータル画面実装のAPI契約に基づき、合成レスポンスでテストしています。
2026-09-12に通常プロジェクト1件で一覧・詳細・資源・ユーザー・ポイント・全5種の概要APIと、
最近7日のHTMLレポートの取得・表解析を実APIで確認しました。ほかのプロジェクト種別・権限差は未確認です。
任意期間 `2026-09-05 00`〜`2026-09-12 00` の英語レポート、HTMLファイル保存、
ユーザー一覧のページ指定と並べ替え、`--hours 24` のレポート取得も実行して確認済みです。
APIの接続先は既定で `https://oprpl.mdx.jp/api`。`MDX_BASE_URL` には既存仕様どおり
`https://oprpl.mdx.jp`（`/api` なし）を指定します。認証は既存の `Authorization: JWT <token>` を使用し、
通常のAPIクライアントは `Content-Type: application/json` と `Accept-Language: ja` を送信します。

## VM数・ストレージ使用量の集約

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
