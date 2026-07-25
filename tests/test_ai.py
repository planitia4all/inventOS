from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.ai.base import AIProviderError
from src.ai.mock_provider import MockAIProvider
from src.ai.providers.factory import get_ai_provider
from src.config.settings import Settings
from src.inventions.schemas import InventionInput
from src.inventions.service import InventionService
from src.patents.schemas import ManualPatentInput
from src.patents.service import PatentService


def make_invention(session):
    return InventionService(session).create(
        InventionInput(
            title="유리기판 관통전극",
            original_idea="금속 핀을 먼저 배열하고 유리를 성형한다.",
            core_principle="금속 핀 선배치 후 유리 성형",
        )
    )


def make_patent(session, invention_id):
    service = PatentService(session)
    link = service.register_manual(
        invention_id,
        ManualPatentInput(
            title="선행특허",
            publication_number="KR-0001",
            abstract_original="금속 와이어를 이용한 유리기판 관통전극 형성 방법.",
        ),
    )
    return link


def test_mock_provider_generate_search_terms(db_session):
    invention = make_invention(db_session)
    provider = MockAIProvider()
    terms = provider.generate_search_terms(invention)
    assert terms.recommended_queries
    assert invention.title in terms.recommended_queries


def test_mock_provider_translate_and_summarize(db_session):
    invention = make_invention(db_session)
    link = make_patent(db_session, invention.id)
    provider = MockAIProvider()

    translated = provider.translate_abstract(link.patent.abstract_original, "en")
    assert "Mock 번역" in translated

    summary = provider.summarize_patent(link.patent)
    assert "Mock 요약" in summary


def test_mock_provider_compare_returns_draft(db_session):
    invention = make_invention(db_session)
    link = make_patent(db_session, invention.id)
    provider = MockAIProvider()

    draft = provider.compare_invention_and_patent(invention, link.patent)
    assert draft.confidence == 0
    assert draft.similarities


def test_factory_falls_back_to_mock_without_api_key():
    settings = Settings(ai_provider="anthropic", anthropic_api_key="")
    provider, warning = get_ai_provider(settings)
    assert provider.name == "mock"
    assert warning is not None


def test_factory_falls_back_to_mock_on_unknown_provider():
    settings = Settings(ai_provider="unknown-provider")
    provider, warning = get_ai_provider(settings)
    assert provider.name == "mock"
    assert warning is not None


def test_factory_uses_mock_by_default():
    settings = Settings(ai_provider="mock")
    provider, warning = get_ai_provider(settings)
    assert provider.name == "mock"
    assert warning is None


def test_anthropic_provider_requires_api_key():
    from src.ai.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(AIProviderError):
        AnthropicProvider(api_key="")


def test_anthropic_provider_parses_json_response(monkeypatch, db_session):
    from src.ai.providers.anthropic_provider import AnthropicProvider

    invention = make_invention(db_session)

    payload = {
        "korean_keywords": ["관통전극"],
        "english_keywords": ["through electrode"],
        "synonyms": [],
        "materials": [],
        "processes": [],
        "device_terms": [],
        "functional_phrases": [],
        "ipc_candidates": [],
        "cpc_candidates": [],
        "recommended_queries": ["관통전극"],
    }
    fake_response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
    )

    provider = AnthropicProvider(api_key="dummy-key")
    monkeypatch.setattr(
        provider._client.messages, "create", lambda **kwargs: fake_response
    )

    terms = provider.generate_search_terms(invention)
    assert terms.korean_keywords == ["관통전극"]


def test_anthropic_provider_raises_on_refusal(monkeypatch, db_session):
    from src.ai.providers.anthropic_provider import AnthropicProvider

    invention = make_invention(db_session)
    fake_response = SimpleNamespace(stop_reason="refusal", content=[])

    provider = AnthropicProvider(api_key="dummy-key")
    monkeypatch.setattr(
        provider._client.messages, "create", lambda **kwargs: fake_response
    )

    with pytest.raises(AIProviderError):
        provider.generate_search_terms(invention)


def test_anthropic_provider_raises_on_invalid_json(monkeypatch, db_session):
    from src.ai.providers.anthropic_provider import AnthropicProvider

    invention = make_invention(db_session)
    fake_response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="not json")],
    )

    provider = AnthropicProvider(api_key="dummy-key")
    monkeypatch.setattr(
        provider._client.messages, "create", lambda **kwargs: fake_response
    )

    with pytest.raises(AIProviderError):
        provider.generate_search_terms(invention)
