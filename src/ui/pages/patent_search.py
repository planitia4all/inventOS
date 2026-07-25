"""선행특허 검색·등록·비교 화면 (발명 상세 화면 우측/하단에 배치).

Phase 2: 수동 등록 + 비교 기록.
Phase 3: PatentProvider.search를 통한 자동/수동 검색어 검색 + TF-IDF 유사도.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src.ai.base import AIProviderError
from src.ai.providers.factory import get_ai_provider
from src.config.settings import get_settings
from src.database.engine import get_session
from src.inventions.service import InventionService
from src.patents.providers.base import PatentDetail, PatentProviderError
from src.patents.providers.factory import PROVIDER_LABELS, available_search_providers, get_provider
from src.patents.schemas import IMPORTANCE_VALUES, REVIEW_STATUS_VALUES, ComparisonInput, ManualPatentInput
from src.patents.service import DuplicatePatentLinkError, PatentService
from src.similarity.tfidf import calculate_similarity


def _results_key(invention_id: str) -> str:
    return f"patent_search_results_{invention_id}"


def _render_ai_search_terms(invention_id: str, invention) -> None:
    settings = get_settings()
    if st.button("AI 검색어 생성", key=f"ai_terms_btn_{invention_id}"):
        provider, warning = get_ai_provider(settings)
        if warning:
            st.info(warning)
        try:
            terms = provider.generate_search_terms(invention)
            st.session_state[f"ai_terms_{invention_id}"] = terms
        except AIProviderError as exc:
            st.error(
                f"AI 검색어 생성에 실패했습니다.\n\n{exc}\n\n수동으로 검색어를 입력할 수 있습니다."
            )

    terms = st.session_state.get(f"ai_terms_{invention_id}")
    if terms:
        with st.expander("AI 생성 검색어 (선택 시 검색어에 적용)", expanded=True):
            st.caption("AI 생성 결과")
            if terms.korean_keywords:
                st.markdown(f"- 한국어 키워드: {', '.join(terms.korean_keywords)}")
            if terms.english_keywords:
                st.markdown(f"- 영어 키워드: {', '.join(terms.english_keywords)}")
            if terms.ipc_candidates:
                st.markdown(f"- IPC 후보: {', '.join(terms.ipc_candidates)}")
            if terms.cpc_candidates:
                st.markdown(f"- CPC 후보: {', '.join(terms.cpc_candidates)}")
            for i, query in enumerate(terms.recommended_queries):
                if st.button(f"'{query}' 검색어로 사용", key=f"use_query_{invention_id}_{i}"):
                    st.session_state[f"query_{invention_id}"] = query
                    st.rerun()


def _render_search_section(invention_id: str, service: PatentService, session) -> None:
    settings = get_settings()
    invention = InventionService(session).get(invention_id)
    invention_text = " ".join(
        filter(
            None,
            [
                invention.original_idea if invention else "",
                invention.problem_to_solve if invention else "",
                invention.core_principle if invention else "",
            ],
        )
    )

    st.markdown("**선행특허 검색**")
    st.caption(
        "유사도는 텍스트 기반 참고 점수이며, 신규성·진보성·특허침해에 대한 "
        "법적 판단이 아닙니다."
    )

    _render_ai_search_terms(invention_id, invention)

    provider_keys = available_search_providers(settings)
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input(
            "검색어 (직접 입력)", key=f"query_{invention_id}",
            help="쉼표로 여러 검색어를 구분할 수 있습니다.",
        )
    with col2:
        provider_key = st.selectbox(
            "데이터 공급자",
            provider_keys,
            format_func=lambda k: PROVIDER_LABELS.get(k, k),
            key=f"provider_{invention_id}",
        )

    if st.button("검색", key=f"search_btn_{invention_id}"):
        if not query.strip():
            st.warning("검색어를 입력하세요.")
        else:
            try:
                provider = get_provider(provider_key, settings)
                results = provider.search(query.strip(), limit=settings.default_search_limit)
                scored = []
                for r in results:
                    score = calculate_similarity(
                        invention_text, r.title, r.abstract_snippet or ""
                    )
                    scored.append((score, r))
                scored.sort(key=lambda pair: pair[0], reverse=True)
                st.session_state[_results_key(invention_id)] = scored
                if not scored:
                    st.info("검색 결과가 없습니다.")
            except PatentProviderError as exc:
                st.error(
                    f"특허 검색 서비스를 사용할 수 없습니다.\n\n{exc}\n\n"
                    "발명 내용은 정상적으로 저장되었습니다. API 설정을 확인하거나 "
                    "특허를 수동으로 등록할 수 있습니다."
                )

    scored_results = st.session_state.get(_results_key(invention_id), [])
    if scored_results:
        st.caption(f"검색 결과 {len(scored_results)}건 (유사도 높은 순)")
        for score, r in scored_results:
            with st.container(border=True):
                cols = st.columns([5, 1, 1])
                cols[0].markdown(f"**{r.title}**")
                cols[0].caption(
                    f"{r.publication_number} · {r.applicant or '(출원인 미상)'} · "
                    f"{r.country_code or '-'} · 우선일 "
                    f"{r.priority_date.isoformat() if r.priority_date else '(미상)'} · "
                    f"공급자: {PROVIDER_LABELS.get(r.provider, r.provider)}"
                )
                snippet = (r.abstract_snippet or "")[:200]
                if snippet:
                    cols[0].write(snippet + ("..." if len(r.abstract_snippet or "") >= 200 else ""))
                cols[1].metric("유사도", f"{score:.0f}")
                if cols[2].button("연결", key=f"link_{invention_id}_{r.publication_number}"):
                    try:
                        provider = get_provider(r.provider, settings)
                        try:
                            detail = provider.get_detail(r.publication_number)
                        except (PatentProviderError, NotImplementedError, LookupError):
                            detail = PatentDetail(
                                provider=r.provider,
                                provider_document_id=r.provider_document_id,
                                publication_number=r.publication_number,
                                title=r.title,
                                abstract_original=r.abstract_snippet,
                                applicant=r.applicant,
                                priority_date=r.priority_date,
                                country_code=r.country_code,
                                raw_data_json=r.raw_data_json,
                            )
                        service.register_from_detail(invention_id, detail)
                        st.success("선행특허가 발명에 연결되었습니다.")
                        st.rerun()
                    except DuplicatePatentLinkError as exc:
                        st.warning(str(exc))
                    except PatentProviderError as exc:
                        st.error(str(exc))


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


def _render_linked_patents(invention_id: str, service: PatentService, session) -> None:
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

                ai_cols = st.columns(3)
                settings = get_settings()
                if ai_cols[0].button("AI 번역", key=f"ai_translate_{link.id}"):
                    provider, warning = get_ai_provider(settings)
                    if warning:
                        st.info(warning)
                    try:
                        translated = provider.translate_abstract(
                            patent.abstract_original or "", patent.abstract_language or ""
                        )
                        service.save_patent_translation(patent.id, translated)
                        st.rerun()
                    except AIProviderError as exc:
                        st.error(f"AI 번역에 실패했습니다.\n\n{exc}")
                if ai_cols[1].button("AI 요약", key=f"ai_summarize_{link.id}"):
                    provider, warning = get_ai_provider(settings)
                    if warning:
                        st.info(warning)
                    try:
                        summary = provider.summarize_patent(patent)
                        service.save_patent_ai_summary(patent.id, summary)
                        st.rerun()
                    except AIProviderError as exc:
                        st.error(f"AI 요약에 실패했습니다.\n\n{exc}")
                if ai_cols[2].button("AI 비교 초안 생성", key=f"ai_compare_{link.id}"):
                    provider, warning = get_ai_provider(settings)
                    if warning:
                        st.info(warning)
                    try:
                        invention = InventionService(session).get(invention_id)
                        draft = provider.compare_invention_and_patent(invention, patent)
                        service.save_ai_comparison_draft(link.id, draft.to_dict())
                        st.rerun()
                    except AIProviderError as exc:
                        st.error(f"AI 비교 초안 생성에 실패했습니다.\n\n{exc}")

                if link.ai_comparison_json:
                    with st.expander("AI 생성 비교 초안 (검토 후 적용 필요)", expanded=True):
                        draft = link.ai_comparison_json
                        st.caption(
                            "AI 생성 초안 — 신규성·진보성에 대한 법적 판단이 아닌 참고용입니다."
                        )
                        st.markdown(f"- 같은 점: {'; '.join(draft.get('similarities', []))}")
                        st.markdown(f"- 다른 점: {'; '.join(draft.get('differences', []))}")
                        st.markdown(
                            f"- 선행특허 핵심: {draft.get('prior_patent_core', '')}"
                        )
                        st.markdown(
                            "- 차별화 아이디어: "
                            + "; ".join(draft.get("possible_differentiators", []))
                        )
                        st.markdown(f"- 신뢰도(참고용): {draft.get('confidence', 0)}")
                        if st.button("이 초안을 비교 기록에 적용", key=f"apply_draft_{link.id}"):
                            service.apply_ai_comparison_draft(link.id)
                            st.success("AI 초안이 비교 기록에 적용되었습니다.")
                            st.rerun()

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
        _render_search_section(invention_id, service, session)
        st.divider()
        _render_manual_form(invention_id, service)
        st.divider()
        _render_linked_patents(invention_id, service, session)
