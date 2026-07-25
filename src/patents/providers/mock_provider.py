"""테스트/데모용 Mock 특허 Provider.

API 키 없이도 검색 UI를 확인할 수 있도록 고정된 데모 데이터를 반환한다.
반환되는 모든 데이터는 실제 특허가 아니므로 명확히 표시한다.
"""
from __future__ import annotations

from datetime import date

from src.patents.providers.base import PatentDetail, PatentSearchResult

_MOCK_LABEL = "[실제 특허가 아닌 테스트 데이터]"

_MOCK_PATENTS = [
    {
        "publication_number": "US-MOCK-0000001-A1",
        "title": f"{_MOCK_LABEL} Metal wire embedded glass substrate with through electrode",
        "applicant": "Mock Glass Tech Inc.",
        "priority_date": date(2021, 3, 15),
        "country_code": "US",
        "abstract": (
            "A glass substrate is formed around pre-arranged metal wires so that the "
            "wires themselves function as through electrodes, without a separate via "
            "hole drilling process. (Mock data for demonstration only.)"
        ),
    },
    {
        "publication_number": "KR-MOCK-0000002-A",
        "title": f"{_MOCK_LABEL} 금속 핀 매립형 유리기판 관통전극 제조방법",
        "applicant": "목업전자(주)",
        "priority_date": date(2020, 11, 2),
        "country_code": "KR",
        "abstract": (
            "금속 핀을 먼저 배열한 뒤 주변에 유리를 성형하여 별도의 비아 홀 가공 "
            "없이 관통전극을 형성하는 유리기판 제조방법. (데모용 예시 데이터입니다.)"
        ),
    },
]


class MockPatentProvider:
    name = "mock"

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        results = [
            PatentSearchResult(
                provider=self.name,
                provider_document_id=p["publication_number"],
                publication_number=p["publication_number"],
                title=p["title"],
                applicant=p["applicant"],
                priority_date=p["priority_date"],
                country_code=p["country_code"],
                abstract_snippet=p["abstract"][:200],
                raw_data_json={"mock": True},
            )
            for p in _MOCK_PATENTS
        ]
        return results[:limit]

    def get_detail(self, publication_number: str) -> PatentDetail:
        for p in _MOCK_PATENTS:
            if p["publication_number"] == publication_number:
                return PatentDetail(
                    provider=self.name,
                    provider_document_id=p["publication_number"],
                    publication_number=p["publication_number"],
                    title=p["title"],
                    abstract_original=p["abstract"],
                    abstract_language="en" if p["country_code"] == "US" else "ko",
                    applicant=p["applicant"],
                    priority_date=p["priority_date"],
                    filing_date=p["priority_date"],
                    publication_date=p["priority_date"],
                    country_code=p["country_code"],
                    legal_status="확인되지 않음",
                    raw_data_json={"mock": True},
                )
        raise LookupError(f"Mock 데이터에 없는 공개번호입니다: {publication_number}")
