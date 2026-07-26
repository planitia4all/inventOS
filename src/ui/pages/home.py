"""홈 화면.

KPI용 대시보드가 아니라, "지금 무엇을 봐야 하는지"만 보여준다.
새 아이디어 기록 / 검색 / 최근 작성 / 최근 수정 / 검토 필요 /
진행 중 / 즐겨찾기.
"""
from __future__ import annotations

import streamlit as st

from src.database.engine import get_session
from src.inventions.service import InventionService
from src.ui.components.layout import go, idea_card
from src.ui.pages.quick_capture import clear_derive_context

_RECENT_LIMIT = 5


def _tag_names(inv) -> list[str]:
    return [link.tag.name for link in inv.tag_links]


def _card_list(inventions, key_prefix: str, empty_text: str) -> None:
    if not inventions:
        if empty_text:
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
            tags=_tag_names(inv),
        )
        if st.button("열어보기", key=f"{key_prefix}_open_{inv.id}"):
            go("detail", inv.id)


def render() -> None:
    st.title("💡 발명 노트")
    st.caption("떠오른 생각을 먼저 적어두고, 정리는 나중에 하세요.")

    if st.button("➕ 새 아이디어 기록", type="primary", key="home_new"):
        clear_derive_context()
        go("capture")

    keyword = st.text_input(
        "검색", placeholder="제목, 내용, 태그, 첨부파일 이름으로 찾기", key="home_search"
    )

    with get_session() as session:
        service = InventionService(session)

        if keyword and keyword.strip():
            results = service.search(keyword=keyword.strip())
            st.subheader(f"검색 결과 {len(results)}건")
            _card_list(results, "search", "찾는 내용이 없습니다.")
            return

        st.subheader("최근 작성한 아이디어")
        _card_list(
            service.list_recently_created(limit=_RECENT_LIMIT),
            "created",
            "아직 기록한 아이디어가 없습니다. 위의 '새 아이디어 기록'을 눌러 시작하세요.",
        )

        recently_updated = [
            i
            for i in service.list_recently_updated(limit=_RECENT_LIMIT + 5)
            if i.updated_at != i.created_at
        ][:_RECENT_LIMIT]
        if recently_updated:
            st.subheader("최근 수정한 아이디어")
            _card_list(recently_updated, "updated", "")

        needs_review = service.list_needs_review(limit=_RECENT_LIMIT)
        if needs_review:
            st.subheader("검토가 필요한 아이디어")
            st.caption("적어두기만 하고 내용을 채우지 않은 것들입니다.")
            _card_list(needs_review, "review", "")

        in_progress = service.list_in_progress(limit=_RECENT_LIMIT)
        if in_progress:
            st.subheader("진행 중인 발명")
            _card_list(in_progress, "progress", "")

        favorites = service.list_favorites(limit=_RECENT_LIMIT)
        if favorites:
            st.subheader("⭐ 즐겨찾기")
            _card_list(favorites, "fav", "")

    st.divider()
    if st.button("전체 목록 보기", key="home_to_list"):
        go("list")
