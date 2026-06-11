"""VMデプロイ計画

対話/CLI引数で収集した入力を DeployPlan に集約し、APIリクエスト列への変換
（名前パターンのバッチ集約を含む）を純粋関数として提供する。
deploy コマンドの対話部分と実行部分を分離し、計画部分を単体テスト可能にする。
"""

from dataclasses import dataclass

from mdx_cli.commands._name_pattern import (
    expand_name_pattern,
    expand_name_pattern_for_deploy,
)
from mdx_cli.models.template import Template
from mdx_cli.models.vm import VMDeployRequest


@dataclass(frozen=True)
class DeployPlan:
    template: Template
    segment_uuid: str
    name_pattern: str
    disk_size: int
    pack_type: str
    pack_num: int
    service_level: str
    shared_key: str
    power_on: bool

    @property
    def vm_names(self) -> list[str]:
        """展開後の全VM名。"""
        return expand_name_pattern(self.name_pattern)

    @property
    def request_patterns(self) -> list[str]:
        """API範囲記法に集約したリクエスト単位のパターン。"""
        return expand_name_pattern_for_deploy(self.name_pattern)

    def to_requests(self, project_id: str) -> list[VMDeployRequest]:
        """デプロイAPIへのリクエスト列に変換する。"""
        return [
            VMDeployRequest(
                catalog=self.template.uuid,
                project=project_id,
                vm_name=pattern,
                disk_size=self.disk_size,
                pack_type=self.pack_type,
                pack_num=self.pack_num,
                service_level=self.service_level,
                network_adapters=[{"adapter_number": 1, "segment": self.segment_uuid}],
                shared_key=self.shared_key,
                template_name=self.template.template_name or self.template.name,
                os_type=self.template.os_type or "Linux",
                power_on=self.power_on,
            )
            for pattern in self.request_patterns
        ]
