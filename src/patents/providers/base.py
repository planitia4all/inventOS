"""특허 Provider 공통 인터페이스 및 정규화 유틸리티."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


def normalize_publication_number(publication_number: str) -> str:
    """공개번호를 비교 가능한 형태로 정규화한다 (중복 판정용).

    공백/하이픈/점을 제거하고 대문자로 통일한다.
    예: "KR10-2020-0012345 A1" -> "KR1020200012345A1"
    """
    if not publication_number:
        return ""
    return re.sub(r"[\s\-\.]", "", publication_number).upper()


@dataclass
class PatentSearchResult:
    """검색 결과 목록에 표시되는 요약 정보."""

    provider: str
    provider_document_id: str | None
    publication_number: str
    title: str
    applicant: str | None
    priority_date: date | None
    country_code: str | None
    abstract_snippet: str | None
    family_id: str | None = None
    raw_data_json: dict | None = None


@dataclass
class PatentDetail:
    """상세 조회 결과 (PatentDocument로 변환되는 원천 데이터)."""

    provider: str
    provider_document_id: str | None
    publication_number: str
    title: str
    application_number: str | None = None
    registration_number: str | None = None
    abstract_original: str | None = None
    abstract_language: str | None = None
    applicant: str | None = None
    inventors: list[str] = field(default_factory=list)
    priority_date: date | None = None
    filing_date: date | None = None
    publication_date: date | None = None
    country_code: str | None = None
    legal_status: str | None = None
    ipc_codes: list[str] = field(default_factory=list)
    cpc_codes: list[str] = field(default_factory=list)
    family_id: str | None = None
    source_url: str | None = None
    raw_data_json: dict | None = None


class PatentProviderError(Exception):
    """Provider 호출 실패 (네트워크, 인증, 호출 제한 등).

    발생해도 발명 데이터에는 영향을 주지 않아야 한다.
    """


class PatentProvider(Protocol):
    name: str

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        ...

    def get_detail(self, publication_number: str) -> PatentDetail:
        ...
