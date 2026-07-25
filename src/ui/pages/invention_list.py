"""발명 목록 화면."""
from __future__ import annotations

import json

import streamlit as st

from src.database.engine import get_session
from src.inventions.schemas import STATUS_VALUES
from src.inventions.service import InventionService, invention_to_dict
from src.reports.markdown_exporter import export_invention_markdown

TECH_FIELD_ALL = "(전체)"
STATUS_ALL = "(전체)"


def render() -> None:
    st.header("발명 목록")

    with get_session() as session:
        service = InventionService(session)

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            keyword = st.text_input("제목/키워드 검색", key="list_keyword")
        with col2:
            all_inventions = service.list(include_archived=True)
            fields = sorted(
                {inv.technical_field for inv in all_inventions if inv.technical_field}
            )
            technical_field = st.selectbox(
                "기술 분야", [TECH_FIELD_ALL] + fields, key="list_field"
            )
        with col3:
            status = st.selectbox(
                "상태", [STATUS_ALL] + STATUS_VALUES, key="list_status"
            )

        include_archived = st.checkbox("보관된 발명 포함", value=False)

        inventions = service.search(
            keyword=keyword or None,
            technical_field=None if technical_field == TECH_FIELD_ALL else technical_field,
            status=None if status == STATUS_ALL else status,
            include_archived=include_archived,
        )

        st.caption(f"총 {len(inventions)}건")

        if not inventions:
            st.info("등록된 발명이 없습니다. '새 발명' 버튼으로 시작하세요.")
            return

        for inv in inventions:
            with st.container(border=True):
                top = st.columns([3, 1, 1, 1])
                top[0].markdown(
                    f"**{inv.title}**  \n"
                    f"`{inv.invention_no}` · {inv.technical_field or '기술분야 미상'}"
                )
                top[1].markdown(f"상태: **{inv.status}**")
                top[2].markdown(
                    f"작성일: {inv.created_at.strftime('%Y-%m-%d') if inv.created_at else '-'}  \n"
                    f"수정일: {inv.updated_at.strftime('%Y-%m-%d') if inv.updated_at else '-'}"
                )
                top[3].markdown(f"선행특허: {len(inv.patent_links)}건")

                if inv.keywords:
                    st.caption(" ".join(f"#{k}" for k in inv.keywords))

                btns = st.columns(5)
                if btns[0].button("열기", key=f"open_{inv.id}"):
                    st.session_state.page = "detail"
                    st.session_state.current_invention_id = inv.id
                    st.rerun()
                if btns[1].button(
                    "보관" if not inv.is_archived else "보관 해제", key=f"archive_{inv.id}"
                ):
                    service.set_archived(inv.id, not inv.is_archived)
                    st.rerun()

                json_bytes = json.dumps(
                    invention_to_dict(inv), ensure_ascii=False, indent=2
                ).encode("utf-8")
                btns[2].download_button(
                    "JSON",
                    data=json_bytes,
                    file_name=f"{inv.invention_no}.json",
                    mime="application/json",
                    key=f"json_{inv.id}",
                )

                md = export_invention_markdown(inv, list(inv.patent_links))
                btns[3].download_button(
                    "Markdown",
                    data=md.encode("utf-8"),
                    file_name=f"{inv.invention_no}.md",
                    mime="text/markdown",
                    key=f"md_{inv.id}",
                )

                confirm_key = f"confirm_delete_{inv.id}"
                if btns[4].button("삭제", key=f"delete_{inv.id}"):
                    st.session_state[confirm_key] = True

                if st.session_state.get(confirm_key):
                    st.warning(f"'{inv.title}'을(를) 정말 삭제하시겠습니까? 되돌릴 수 없습니다.")
                    c1, c2 = st.columns(2)
                    if c1.button("삭제 확정", key=f"delete_confirm_{inv.id}"):
                        service.delete(inv.id)
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                    if c2.button("취소", key=f"delete_cancel_{inv.id}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
