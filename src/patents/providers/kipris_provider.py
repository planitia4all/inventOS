"""KIPRIS Plus (특허청 특허/실용신안 검색 서비스) 공식 API 연동.

문서: https://plus.kipris.or.kr (개발가이드 > REST OPEN API 활용가이드)
Endpoint: patUtiModInfoSearchSevice / getWordSearch, getBibliographyDetailInfoSearch

주의:
- 이 구현은 공개된 KIPRIS Plus API 문서를 기준으로 작성되었으며, 실제 서비스
  키로 실시간 검증되지 않았다. 응답 XML의 필드명은 KIPRIS 쪽에서 변경될 수
  있으므로, 실제 서비스 키를 발급받은 뒤 `_parse_search_item`/`_parse_detail`의
  필드 매핑을 반드시 재검증해야 한다.
- API 키가 없거나 호출이 실패해도 예외를 PatentProviderError로 감싸서
  전달한다. 이 예외는 상위 서비스에서 잡아 UI에 안내 메시지로만 표시하고,
  발명 데이터 저장 등 나머지 기능에는 영향을 주지 않는다.
"""
from __future__ import annotations

from datetime import date
from xml.etree import ElementTree

import httpx

from src.patents.providers.base import (
    PatentDetail,
    PatentProviderError,
    PatentSearchResult,
)

BASE_URL = "https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice"


def _parse_date(value: str | None) -> date | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def _text(item: ElementTree.Element, tag: str) -> str | None:
    node = item.find(tag)
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text or None


class KiprisProvider:
    name = "kipris"

    def __init__(self, api_key: str, timeout: float = 10.0):
        if not api_key:
            raise PatentProviderError(
                "KIPRIS Plus API 키가 설정되지 않았습니다. 설정 화면에서 "
                "KIPRIS_API_KEY를 등록하거나 특허를 수동으로 등록하세요."
            )
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, path: str, params: dict) -> ElementTree.Element:
        params = {**params, "ServiceKey": self.api_key}
        url = f"{BASE_URL}/{path}"
        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PatentProviderError("KIPRIS Plus API 호출이 시간 초과되었습니다.") from exc
        except httpx.HTTPStatusError as exc:
            raise PatentProviderError(
                f"KIPRIS Plus API 호출에 실패했습니다 (HTTP {exc.response.status_code})."
            ) from exc
        except httpx.HTTPError as exc:
            raise PatentProviderError(
                "특허 검색 서비스에 연결할 수 없습니다. 인터넷 연결을 확인하세요."
            ) from exc

        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError as exc:
            raise PatentProviderError("KIPRIS Plus 응답을 해석할 수 없습니다.") from exc

        result_code = root.findtext(".//resultCode")
        if result_code is not None and result_code not in ("00", "0000", "0"):
            result_msg = root.findtext(".//resultMsg") or "알 수 없는 오류"
            raise PatentProviderError(f"KIPRIS Plus API 오류: {result_msg} ({result_code})")

        return root

    def search(self, query: str, limit: int = 20) -> list[PatentSearchResult]:
        root = self._request(
            "getWordSearch",
            {
                "word": query,
                "patent": "true",
                "utility": "true",
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        results = []
        for item in root.findall(".//item"):
            results.append(self._parse_search_item(item))
        return results

    def _parse_search_item(self, item: ElementTree.Element) -> PatentSearchResult:
        publication_number = (
            _text(item, "publicationNumber") or _text(item, "openNumber") or ""
        )
        abstract = _text(item, "astrtCont")
        return PatentSearchResult(
            provider=self.name,
            provider_document_id=_text(item, "applicationNumber"),
            publication_number=publication_number,
            title=_text(item, "inventionTitle") or "(제목 없음)",
            applicant=_text(item, "applicantName"),
            priority_date=_parse_date(_text(item, "applicationDate")),
            country_code="KR",
            abstract_snippet=(abstract or "")[:200] or None,
            raw_data_json={child.tag: (child.text or "") for child in item},
        )

    def get_detail(self, publication_number: str) -> PatentDetail:
        root = self._request(
            "getBibliographyDetailInfoSearch",
            {"applicationNumber": publication_number},
        )
        item = root.find(".//item")
        if item is None:
            raise PatentProviderError(
                f"공개번호 {publication_number}에 대한 상세정보를 찾을 수 없습니다."
            )

        return PatentDetail(
            provider=self.name,
            provider_document_id=_text(item, "applicationNumber"),
            publication_number=_text(item, "publicationNumber")
            or _text(item, "openNumber")
            or publication_number,
            title=_text(item, "inventionTitle") or "(제목 없음)",
            application_number=_text(item, "applicationNumber"),
            registration_number=_text(item, "registerNumber"),
            abstract_original=_text(item, "astrtCont"),
            abstract_language="ko",
            applicant=_text(item, "applicantName"),
            inventors=[n for n in [_text(item, "inventorName")] if n],
            priority_date=_parse_date(_text(item, "applicationDate")),
            filing_date=_parse_date(_text(item, "applicationDate")),
            publication_date=_parse_date(_text(item, "openDate")),
            country_code="KR",
            legal_status=_text(item, "registerStatus"),
            ipc_codes=[c for c in [_text(item, "ipcNumber")] if c],
            source_url=None,
            raw_data_json={child.tag: (child.text or "") for child in item},
        )
