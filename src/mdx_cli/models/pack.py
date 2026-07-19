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
    vram_per_pack_gb: float = 0

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
        max_num=8, mem_per_pack_gb=57.60, cores_per_pack=18, gpus_per_pack=1, default_num=1,
        vram_per_pack_gb=40,
    ),
}


def pack_choice_label(pack_type: str) -> str:
    """パックタイプ選択肢のラベル（1パックあたりの内訳付き）。"""
    spec = PACK_SPECS[pack_type]
    parts = [f"{spec.cores_per_pack}コア"]
    if spec.gpus_per_pack:
        parts.append(f"{spec.gpus_per_pack}GPU")
    parts.append(f"{spec.mem_per_pack_gb:g}GB RAM")
    if spec.vram_per_pack_gb:
        parts.append(f"{spec.vram_per_pack_gb:g}GB VRAM")
    return f"{pack_type}（1パック = {' / '.join(parts)}）"
