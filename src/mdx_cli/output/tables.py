"""モデルごとのテーブルカラム定義

各定義は (表示名, モデルフィールド名) のタプルのリスト。
"""

VM_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("名前", "name"),
    ("状態", "status"),
    ("サービスレベル", "service_level"),
]

VM_RESOURCE_COLUMNS: list[tuple[str, str]] = [
    ("名前", "name"),
    ("状態", "status"),
    ("パック", "pack"),
    ("CPU", "cpu"),
    ("メモリ", "memory"),
    ("GPU", "gpu"),
    ("ディスク", "disks"),
    ("合計(GB)", "total_gb"),
]

PROJECT_COLUMNS: list[tuple[str, str]] = [
    ("テナント", "tenant"),
    ("UUID", "uuid"),
    ("名前", "name"),
    ("種別", "type"),
    ("期限切れ", "expired"),
    ("停止", "suspended"),
    ("説明", "description"),
]

PROJECT_INFO_FIELDS: list[tuple[str, str]] = [
    ("プロジェクトID", "uuid"), ("名前", "name"), ("種別", "type"),
    ("申請者", "applicant"), ("開始日", "begin"), ("終了日", "limit"), ("説明", "description"),
]

PROJECT_PACK_FIELDS: list[tuple[str, str]] = [
    ("要求量", "_max"), ("使用量", ""), ("割当量", "_max_current"),
    ("翌月割当量", "_future"), ("Rmin", "_rmin"),
]

PROJECT_RESOURCE_FIELDS: list[tuple[str, str]] = [
    ("ディスク", "disk_size"), ("高速ストレージ", "high_speed_storage"),
    ("大容量ストレージ", "large_capacity_storage"), ("オブジェクトストレージ", "object_storage"),
    ("グローバルIP", "global_ip"),
]

PROJECT_USER_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"), ("ユーザー名", "username"), ("メール", "email"), ("権限", "auth"),
]

PROJECT_POINT_COLUMNS: list[tuple[str, str]] = [
    ("ポイント管理番号", "point_id"), ("購入ポイント", "purchase_points"),
    ("利用ポイント", "used_points"), ("残ポイント", "remaining_points"), ("利用期限", "expiration_date"),
]

SEGMENT_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("セグメント名", "name"),
    ("デフォルト", "default"),
]

SEGMENT_SUMMARY_COLUMNS: list[tuple[str, str]] = [
    ("VLAN ID", "vlan_id"),
    ("VNI", "vni"),
    ("IPレンジ", "ip_range"),
]

TASK_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("タイプ", "type"),
    ("対象", "object_name"),
    ("状態", "status"),
    ("進捗", "progress"),
]

DNAT_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("プールアドレス", "pool_address"),
    ("セグメント", "segment"),
    ("宛先アドレス", "dst_address"),
]

ACL_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("プロトコル", "protocol"),
    ("送信元", "src_address"),
    ("送信元マスク", "src_mask"),
    ("送信元ポート", "src_port"),
    ("宛先", "dst_address"),
    ("宛先マスク", "dst_mask"),
    ("宛先ポート", "dst_port"),
]

TEMPLATE_COLUMNS: list[tuple[str, str]] = [
    ("名前", "name"),
    ("OS", "os_name"),
    ("バージョン", "os_version"),
    ("GPU", "gpu_required"),
    ("最小Disk", "lower_limit_disk"),
    ("最小Mem", "lower_limit_memory"),
    ("ユーザー", "login_username"),
]

ACCESS_KEY_COLUMNS: list[tuple[str, str]] = [
    ("UUID", "uuid"),
    ("名前", "name"),
]

HISTORY_COLUMNS: list[tuple[str, str]] = [
    ("タスクID", "uuid"),
    ("操作種別", "type"),
    ("対象", "object_name"),
    ("状態", "status"),
    ("開始", "start_datetime"),
    ("終了", "end_datetime"),
    ("ユーザー", "user_name"),
]
