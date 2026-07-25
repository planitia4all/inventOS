"""선행특허 검색·등록·비교 화면 (발명 상세 화면 우측/하단에 배치).

Phase 2: 수동 등록 + 비교 기록.
Phase 3에서 자동 검색(PatentProvider.search)이 이 파일 상단에 추가된다.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src.database.engine import get_session
from src.patents.schemas import IMPORTANCE_VALUES, REVIEW_STATUS_VALUES, ComparisonInput, ManualPatentInput
from src.patents.service import DuplicatePatentLinkError, PatentService


def _render_manual_form(invention_id: str, service: PatentService) -> None:
    with st.expander("특허 수동 등록", expanded=False):
        with st.form(f"manual_patent_form_{invention_id}"):
            title = st.text_input("발명의 명칭 *")
            publication_number = st.text_input("공개번호 *")
            application_number = st.text_input("출원번호")
            applicant = st.text_input("출원인")
            has_priority_date = st.checkbox("우선일 입력", value=False)
            priority_date = (
                st.date_input("우선일", value=date.today()) if has_priority_date else None
            )
            country_code = st.text_input("국가 (예: KR, US, EP, WO)")
            abstract_original = st.text_area("초록 원문", height=120)
            source_url = st.text_input("특허 URL")
            note = st.text_area("비고")

            submitted = st.form_submit_button("등록")

        if submitted:
            data = ManualPatentInput(
                title=title,
                publication_number=publication_number,
                applicant=applicant or None,
                application_number=application_number or None,
                priority_date=priority_date,
                country_code=country_code or None,
                abstract_original=abstract_original or None,
                source_url=source_url or None,
                note=note or None,
            )
            errors = data.validate()
            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    service.register_manual(invention_id, data)
                    st.success("특허가 등록되고 발명에 연결되었습니다. (데이터 출처: 사용자 입력)")
                    st.rerun()
                except DuplicatePatentLinkError as exc:
                    st.warning(str(exc))


def _render_linked_patents(invention_id: str, service: PatentService) -> None:
    links = service.list_for_invention(invention_id)
    st.subheader(f"연결된 선행특허 ({len(links)}건)")

    if not links:
        st.caption("아직 연결된 선행특허가 없습니다.")
        return

    for link in links:
        patent = link.patent
        title = f"{patent.title}  ·  {patent.publication_number}"
        with st.expander(title, expanded=False):
            info_cols = st.columns(2)
            with info_cols[0]:
                st.markdown("**특허 기본정보**")
                st.markdown(f"- 공개번호: {patent.publication_number}")
                st.markdown(f"- 출원번호: {patent.application_number or '(없음)'}")
                st.markdown(f"- 등록번호: {patent.registration_number or '(없음)'}")
                st.markdown(f"- 출원인: {patent.applicant or '(미상)'}")
                st.markdown(
                    f"- 발명자: {', '.join(patent.inventors) if patent.inventors else '(미상)'}"
                )
                st.markdown(
                    f"- 우선일: {patent.priority_date.isoformat() if patent.priority_date else '(미상)'}"
                )
                st.markdown(f"- 국가: {patent.country_code or '(미상)'}")
                st.markdown(f"- 법적 상태: {patent.legal_status or '확인되지 않음'}")
                st.markdown(f"- 데이터 공급자: {patent.provider}")
                if patent.source_url:
                    st.markdown(f"- [원문 링크]({patent.source_url})")
                st.caption(f"마지막 조회: {patent.fetched_at.strftime('%Y-%m-%d %H:%M')}")

            with info_cols[1]:
                st.markdown("**초록**")
                st.text_area(
                    "원문 초록 (수정 불가)",
                    value=patent.abstract_original or "(초록 없음)",
                    disabled=True,
                    key=f"abstract_{link.id}",
                )
                if patent.abstract_translated_ko:
                    st.caption("AI 생성 번역")
                    st.write(patent.abstract_translated_ko)
                if patent.abstract_ai_summary:
                    st.caption("AI 생성 요약")
                    st.write(patent.abstract_ai_summary)

            st.markdown("---")
            st.markdown("**내 비교 기록**")
            with st.form(f"comparison_form_{link.id}"):
                similarities = st.text_area(
                    "내 아이디어와 같은 점", value=link.similarities or ""
                )
                differences = st.text_area(
                    "내 아이디어와 다른 점", value=link.differences or ""
                )
                patent_solved_problem = st.text_area(
                    "선행특허가 해결한 문제", value=link.patent_solved_problem or ""
                )
                unsolved_problem = st.text_area(
                    "선행특허가 해결하지 못한 문제", value=link.unsolved_problem or ""
                )
                differentiation_ideas = st.text_area(
                    "회피 또는 차별화 아이디어", value=link.differentiation_ideas or ""
                )
                additional_research = st.text_area(
                    "추가 조사 필요사항", value=link.additional_research or ""
                )
                user_notes = st.text_area("기타 메모", value=link.user_notes or "")

                c1, c2 = st.columns(2)
                importance = c1.selectbox(
                    "중요도",
                    IMPORTANCE_VALUES,
                    index=IMPORTANCE_VALUES.index(link.importance)
                    if link.importance in IMPORTANCE_VALUES
                    else 2,
                )
                review_status = c2.selectbox(
                    "검토 상태",
                    REVIEW_STATUS_VALUES,
                    index=REVIEW_STATUS_VALUES.index(link.review_status)
                    if link.review_status in REVIEW_STATUS_VALUES
                    else 0,
                )

                save = st.form_submit_button("비교 기록 저장")

            if save:
                service.update_comparison(
                    link.id,
                    ComparisonInput(
                        similarities=similarities or None,
                        differences=differences or None,
                        patent_solved_problem=patent_solved_problem or None,
                        unsolved_problem=unsolved_problem or None,
                        differentiation_ideas=differentiation_ideas or None,
                        additional_research=additional_research or None,
                        user_notes=user_notes or None,
                        importance=importance,
                        review_status=review_status,
                    ),
                )
                st.success("비교 기록이 저장되었습니다.")
                st.rerun()

            if st.button("연결 해제", key=f"unlink_{link.id}"):
                service.delete_link(link.id)
                st.rerun()


def render(invention_id: str) -> None:
    st.subheader("선행특허 검색·등록")

    with get_session() as session:
        service = PatentService(session)
        _render_manual_form(invention_id, service)
        st.divider()
        _render_linked_patents(invention_id, service)
