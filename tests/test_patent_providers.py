from __future__ import annotations

import httpx
import pytest

from src.patents.providers.base import PatentProviderError
from src.patents.providers.kipris_provider import KiprisProvider
from src.patents.providers.mock_provider import MockPatentProvider


def test_mock_provider_search_returns_labeled_demo_data():
    provider = MockPatentProvider()
    results = provider.search("유리기판", limit=10)
    assert len(results) == 2
    assert all("실제 특허가 아닌 테스트 데이터" in r.title for r in results)


def test_mock_provider_get_detail_returns_abstract():
    provider = MockPatentProvider()
    results = provider.search("아무거나")
    detail = provider.get_detail(results[0].publication_number)
    assert detail.abstract_original


def test_kipris_provider_requires_api_key():
    with pytest.raises(PatentProviderError):
        KiprisProvider(api_key="")


_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
  <body>
    <items>
      <item>
        <inventionTitle>금속 핀 매립 유리기판</inventionTitle>
        <applicationNumber>1020200012345</applicationNumber>
        <publicationNumber>1020210012345</publicationNumber>
        <applicantName>테스트출원인</applicantName>
        <applicationDate>20200101</applicationDate>
        <astrtCont>금속 핀을 먼저 배열한다.</astrtCont>
      </item>
    </items>
  </body>
</response>
"""

_ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>99</resultCode><resultMsg>SERVICE KEY IS NOT REGISTERED</resultMsg></header>
  <body></body>
</response>
"""


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://plus.kipris.or.kr/mock")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


def test_kipris_provider_parses_search_results(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(_SEARCH_XML)

    monkeypatch.setattr(httpx, "get", fake_get)

    provider = KiprisProvider(api_key="dummy-key")
    results = provider.search("유리기판")

    assert len(results) == 1
    assert results[0].title == "금속 핀 매립 유리기판"
    assert results[0].publication_number == "1020210012345"
    assert results[0].applicant == "테스트출원인"


def test_kipris_provider_raises_on_result_code_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResponse(_ERROR_XML)

    monkeypatch.setattr(httpx, "get", fake_get)

    provider = KiprisProvider(api_key="dummy-key")
    with pytest.raises(PatentProviderError):
        provider.search("유리기판")


def test_kipris_provider_raises_friendly_error_on_network_failure(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(httpx, "get", fake_get)

    provider = KiprisProvider(api_key="dummy-key")
    with pytest.raises(PatentProviderError):
        provider.search("유리기판")
