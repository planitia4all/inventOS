"""수동 등록 Provider.

이 Provider는 외부 검색을 수행하지 않는다. UI의 수동 등록 폼(요구사항 8절)이
직접 `PatentService.register_manual`을 호출하므로, 이 클래스는 Provider
목록에 "사용자 입력"이 항상 선택 가능한 옵션으로 노출되도록 자리를 채우는
역할만 한다.
"""
from __future__ import annotations

from src.patents.providers.base import PatentDetail, PatentProviderError, PatentSearchResult


class ManualPatentProvider:
    name = "manual"

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        return []

    def get_detail(self, publication_number: str) -> PatentDetail:
        raise PatentProviderError(
            "수동 등록 Provider는 상세 조회를 지원하지 않습니다. "
            "발명 상세 화면의 '특허 수동 등록' 폼을 사용하세요."
        )
