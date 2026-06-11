"""MDXパック仕様（CPU/GPUパックのリソース定数）

deploy / reconfigure で共有する。値はMDXポータルの仕様に合わせる。
"""

from typing import NamedTuple


class PackSpec(NamedTuple):
    max_num: int  # 1VMあたりの最大パック数
    mem_per_pack_gb: float
    cores_per_pack: int
    gpus_per_pack: int
    default_num: int  # 対話入力時のデフォルト

    def resource_summary(self, pack_num: int) -> str:
        """パック数に応じたリソース内訳の表示文字列。"""
        cores = pack_num * self.cores_per_pack
        mem = pack_num * self.mem_per_pack_gb
        if self.gpus_per_pack:
            return f"{cores}コア / {pack_num * self.gpus_per_pack}GPU / {mem:.1f}GB RAM"
        return f"{cores}コア / {mem:.1f}GB RAM"


PACK_SPECS: dict[str, PackSpec] = {
    "cpu": PackSpec(
        max_num=152, mem_per_pack_gb=1.51, cores_per_pack=1, gpus_per_pack=0, default_num=3
    ),
    "gpu": PackSpec(
        max_num=8, mem_per_pack_gb=57.60, cores_per_pack=18, gpus_per_pack=1, default_num=1
    ),
}
