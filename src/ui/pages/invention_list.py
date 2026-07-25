"""전체 목록 화면.

모바일에서 표는 읽기 어려우므로 카드로 표시한다. 필터는 상태 하나만
남기고, 나머지 고급 기능은 상세 화면으로 옮겼다.
"""
from __future__ import annotations

import streamlit as st

from src.database.engine import get_session
from src.inventions.schemas import STATUS_VALUES
from src.inventions.service import InventionService
from src.ui.components.layout import go, idea_card

_STATUS_ALL = "전체"


def render() -> None:
    st.title("전체 목록")

    if st.button("➕ 새 아이디어 기록", type="primary", key="list_new"):
        go("capture")

    keyword = st.text_input("검색", placeholder="제목이나 내용으로 찾기", key="list_search")

    with st.expander("자세한 조건", expanded=False):
        status = st.selectbox("상태", [_STATUS_ALL] + STATUS_VALUES, key="list_status")
        include_archived = st.checkbox("보관한 것도 보기", value=False, key="list_arch")

    with get_session() as session:
        service = InventionService(session)
        inventions = service.search(
            keyword=(keyword or "").strip() or None,
            status=None if status == _STATUS_ALL else status,
            include_archived=include_archived,
        )

        st.caption(f"{len(inventions)}건")
        if not inventions:
            st.info("기록한 아이디어가 없습니다.")
            return

        for inv in inventions:
            meta = f"{inv.updated_at.strftime('%Y-%m-%d')} · {inv.status}"
            if inv.patent_links:
                meta += f" · 비슷한 기술 {len(inv.patent_links)}건"
            if inv.is_archived:
                meta += " · 보관됨"

            idea_card(
                title=("⭐ " if inv.is_favorite else "") + inv.title,
                meta=meta,
                body=inv.original_idea,
                tags=inv.keywords or [],
            )
            if st.button("열어보기", key=f"list_open_{inv.id}"):
                go("detail", inv.id)
