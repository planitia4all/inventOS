"""발명 상세(작성/수정) 화면."""
from __future__ import annotations

import json

import streamlit as st

from src.attachments.service import AttachmentError, AttachmentService
from src.database.engine import get_session
from src.inventions.schemas import STATUS_VALUES, InventionInput
from src.inventions.service import InventionService, invention_to_dict
from src.reports.markdown_exporter import export_invention_markdown


def _keywords_from_text(text: str) -> list[str]:
    return [k.strip() for k in text.replace("\n", ",").split(",") if k.strip()]


def render(invention_id: str | None) -> None:
    with get_session() as session:
        service = InventionService(session)
        invention = service.get(invention_id) if invention_id else None

        if invention_id and invention is None:
            st.error("발명을 찾을 수 없습니다.")
            return

        header = f"{invention.invention_no} / {invention.title}" if invention else "새 발명"
        st.header(header)
        if invention:
            st.caption(
                f"상태: {invention.status} · 기술분야: {invention.technical_field or '(미상)'} · "
                f"작성일: {invention.created_at.strftime('%Y-%m-%d') if invention.created_at else '-'} · "
                f"최근 수정일: {invention.updated_at.strftime('%Y-%m-%d') if invention.updated_at else '-'} · "
                f"버전: v{invention.version}"
            )

        left, right = st.columns([3, 2])

        with left:
            st.subheader("발명 내용")
            with st.form("invention_form", clear_on_submit=False):
                title = st.text_input("발명 제목 *", value=invention.title if invention else "")
                technical_field = st.text_input(
                    "기술 분야", value=invention.technical_field if invention else ""
                )
                original_idea = st.text_area(
                    "최초 아이디어 *",
                    value=invention.original_idea if invention else "",
                    height=120,
                )
                problem_to_solve = st.text_area(
                    "해결하려는 문제",
                    value=invention.problem_to_solve if invention else "",
                )
                conventional_method = st.text_area(
                    "기존 방식", value=invention.conventional_method if invention else ""
                )
                conventional_problems = st.text_area(
                    "기존 방식의 문제점",
                    value=invention.conventional_problems if invention else "",
                )
                core_principle = st.text_area(
                    "핵심 해결 원리", value=invention.core_principle if invention else ""
                )
                expected_effects = st.text_area(
                    "예상 효과", value=invention.expected_effects if invention else ""
                )
                technical_barriers = st.text_area(
                    "예상 기술 장벽", value=invention.technical_barriers if invention else ""
                )
                applicable_industries = st.text_area(
                    "적용 가능한 산업",
                    value=invention.applicable_industries if invention else "",
                )
                keywords_text = st.text_input(
                    "관련 키워드 (쉼표로 구분)",
                    value=", ".join(invention.keywords) if invention else "",
                )
                inventor_name = st.text_input(
                    "작성자", value=invention.inventor_name if invention else ""
                )
                status = st.selectbox(
                    "상태",
                    STATUS_VALUES,
                    index=STATUS_VALUES.index(invention.status)
                    if invention and invention.status in STATUS_VALUES
                    else 0,
                )

                submitted = st.form_submit_button("저장", type="primary")

            if submitted:
                data = InventionInput(
                    title=title,
                    original_idea=original_idea,
                    technical_field=technical_field or None,
                    problem_to_solve=problem_to_solve or None,
                    conventional_method=conventional_method or None,
                    conventional_problems=conventional_problems or None,
                    core_principle=core_principle or None,
                    expected_effects=expected_effects or None,
                    technical_barriers=technical_barriers or None,
                    applicable_industries=applicable_industries or None,
                    keywords=_keywords_from_text(keywords_text),
                    inventor_name=inventor_name or None,
                    status=status,
                )
                errors = data.validate()
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    try:
                        if invention:
                            invention = service.update(invention.id, data)
                            st.success("저장되었습니다.")
                        else:
                            invention = service.create(data)
                            st.session_state.current_invention_id = invention.id
                            st.success(f"새 발명이 등록되었습니다: {invention.invention_no}")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

            if invention:
                st.divider()
                st.subheader("버전 관리")
                change_note = st.text_input("변경 메모", key="revision_note")
                if st.button("버전 저장"):
                    service.save_revision(invention.id, change_note=change_note or None)
                    st.success("현재 상태가 새 버전으로 저장되었습니다.")
                    st.rerun()

                revisions = service.list_revisions(invention.id)
                if revisions:
                    with st.expander(f"버전 이력 ({len(revisions)}건)"):
                        for rev in revisions:
                            st.markdown(
                                f"- v{rev.revision_no} · "
                                f"{rev.created_at.strftime('%Y-%m-%d %H:%M')} · "
                                f"{rev.change_note or '(메모 없음)'}"
                            )

                st.divider()
                st.subheader("첨부파일")
                attachment_service = AttachmentService(session)
                uploaded = st.file_uploader(
                    "이미지 또는 PDF 첨부", type=["png", "jpg", "jpeg", "pdf"]
                )
                if uploaded is not None and st.button("첨부 저장"):
                    try:
                        attachment_service.save(
                            invention.id,
                            uploaded.name,
                            uploaded.getvalue(),
                            content_type=uploaded.type,
                        )
                        st.success("첨부파일이 저장되었습니다.")
                        st.rerun()
                    except AttachmentError as exc:
                        st.error(str(exc))

                attachments = attachment_service.list_for_invention(invention.id)
                for att in attachments:
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"📎 {att.original_filename}")
                    if c2.button("삭제", key=f"del_att_{att.id}"):
                        attachment_service.delete(att)
                        st.rerun()

                st.divider()
                st.subheader("내보내기")
                json_bytes = json.dumps(
                    invention_to_dict(invention), ensure_ascii=False, indent=2
                ).encode("utf-8")
                st.download_button(
                    "JSON 내보내기",
                    data=json_bytes,
                    file_name=f"{invention.invention_no}.json",
                    mime="application/json",
                )
                md = export_invention_markdown(invention, list(invention.patent_links))
                st.download_button(
                    "Markdown 보고서 내보내기",
                    data=md.encode("utf-8"),
                    file_name=f"{invention.invention_no}.md",
                    mime="text/markdown",
                )

        with right:
            if invention:
                from src.ui.pages import patent_search

                patent_search.render(invention.id)
            else:
                st.info("발명을 먼저 저장하면 선행특허 검색을 사용할 수 있습니다.")
