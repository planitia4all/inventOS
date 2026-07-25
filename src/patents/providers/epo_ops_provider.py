"""EPO OPS (Open Patent Services) Provider.

MVP 범위에서는 구현하지 않는다 (요구사항 16절: 공식 API는 1개만 우선 연동).
Provider 목록에서 선택할 수 있도록 인터페이스만 채워두고, 실제 호출 시에는
안내 메시지와 함께 PatentProviderError를 발생시킨다.
"""
from __future__ import annotations

from src.patents.providers.base import PatentDetail, PatentProviderError, PatentSearchResult


class EpoOpsProvider:
    name = "epo_ops"

    def __init__(self, client_key: str, client_secret: str):
        self.client_key = client_key
        self.client_secret = client_secret

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        raise PatentProviderError(
            "EPO OPS 연동은 아직 지원되지 않습니다. KIPRIS Plus를 사용하거나 "
            "특허를 수동으로 등록하세요."
        )

    def get_detail(self, publication_number: str) -> PatentDetail:
        raise PatentProviderError("EPO OPS 연동은 아직 지원되지 않습니다.")
