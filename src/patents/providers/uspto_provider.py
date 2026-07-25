"""USPTO PatentsView / Open Data Portal Provider.

MVP 범위에서는 구현하지 않는다 (요구사항 16절: 공식 API는 1개만 우선 연동).
USPTO는 2026년부터 PatentsView에서 Open Data Portal로 이전 중이므로,
실제 구현 시점의 최신 엔드포인트를 다시 확인해야 한다.
"""
from __future__ import annotations

from src.patents.providers.base import PatentDetail, PatentProviderError, PatentSearchResult


class UsptoProvider:
    name = "uspto"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        raise PatentProviderError(
            "USPTO 연동은 아직 지원되지 않습니다. KIPRIS Plus를 사용하거나 "
            "특허를 수동으로 등록하세요."
        )

    def get_detail(self, publication_number: str) -> PatentDetail:
        raise PatentProviderError("USPTO 연동은 아직 지원되지 않습니다.")
