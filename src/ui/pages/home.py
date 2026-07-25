"""홈 화면.

복잡한 대시보드 대신 다음 네 가지만 둔다.
새 아이디어 기록 / 검색 / 최근 기록 / 아직 정리하지 않은 것과 즐겨찾기.
"""
from __future__ import annotations

import streamlit as st

from src.database.engine import get_session
from src.inventions.service import InventionService
from src.ui.components.layout import go, idea_card

_RECENT_LIMIT = 5


def _card_list(inventions, key_prefix: str, empty_text: str) -> None:
    if not inventions:
        st.caption(empty_text)
        return

    for inv in inventions:
        idea_card(
            title=("⭐ " if inv.is_favorite else "") + inv.title,
            meta=(
                f"{inv.updated_at.strftime('%Y-%m-%d')} · {inv.status}"
                + (f" · 비슷한 기술 {len(inv.patent_links)}건" if inv.patent_links else "")
            ),
            body=inv.original_idea,
            tags=inv.keywords or [],
        )
        if st.button("열어보기", key=f"{key_prefix}_open_{inv.id}"):
            go("detail", inv.id)


def render() -> None:
    st.title("💡 발명 노트")
    st.caption("떠오른 생각을 먼저 적어두고, 정리는 나중에 하세요.")

    if st.button("➕ 새 아이디어 기록", type="primary", key="home_new"):
        go("capture")

    keyword = st.text_input(
        "검색", placeholder="제목이나 내용으로 찾기", key="home_search"
    )

    with get_session() as session:
        service = InventionService(session)

        if keyword and keyword.strip():
            results = service.search(keyword=keyword.strip())
            st.subheader(f"검색 결과 {len(results)}건")
            _card_list(results, "search", "찾는 내용이 없습니다.")
            return

        st.subheader("최근 기록")
        _card_list(
            service.list_recent(limit=_RECENT_LIMIT),
            "recent",
            "아직 기록한 아이디어가 없습니다. 위의 '새 아이디어 기록'을 눌러 시작하세요.",
        )

        needs_review = service.list_needs_review(limit=_RECENT_LIMIT)
        if needs_review:
            st.subheader("아직 정리하지 않은 아이디어")
            st.caption("적어두기만 하고 내용을 채우지 않은 것들입니다.")
            _card_list(needs_review, "review", "")

        favorites = service.list_favorites(limit=_RECENT_LIMIT)
        if favorites:
            st.subheader("⭐ 즐겨찾기")
            _card_list(favorites, "fav", "")

    st.divider()
    if st.button("전체 목록 보기", key="home_to_list"):
        go("list")
