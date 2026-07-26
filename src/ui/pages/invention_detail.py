"""발명 상세 화면.

원본 메모를 맨 위에 그대로 보여주고, 나머지 항목은 내용이 있을 때만
표시한다. 비어 있는 항목은 버튼을 눌러야 펼쳐진다.

쓰기 동작은 모두 `run_and_rerun`을 거쳐 별도의 짧은 세션에서 커밋까지
끝낸 뒤 새로고침한다 (이유는 `src/ui/components/actions.py` 참고).
읽기 전용 표시는 화면 렌더링 동안 열어 두는 공용 세션을 그대로 쓴다.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from src.ai.base import AIProviderError
from src.ai.providers.factory import get_ai_provider
from src.ai.results_service import RESULT_KINDS, AIResultService
from src.ai.review import (
    PARTIAL_APPLY_FIELD_LABELS,
    PARTIAL_APPLY_FIELDS,
    REVIEW_DEFAULT_FIELD,
    REVIEW_GROUPS,
    build_context,
)
from src.attachments.service import (
    ATTACHMENT_CATEGORIES,
    AttachmentError,
    AttachmentService,
    attachment_kind,
)
from src.config.settings import get_settings
from src.database.engine import get_session
from src.drafts.store import DraftStore
from src.experiments.schemas import ExperimentInput
from src.experiments.service import ExperimentService, draft_text_from_experiment
from src.inventions.schemas import DERIVATION_COPY_FIELDS, DETAIL_GROUPS, FIELD_LABELS, STATUS_VALUES
from src.inventions.service import InventionService
from src.reports.markdown_exporter import export_invention_markdown
from src.ui.components.actions import run_and_rerun
from src.ui.components.layout import go
from src.ui.pages.quick_capture import clear_derive_context, start_derive_capture


def _render_header(invention) -> None:
    st.title(invention.title)
    st.caption(
        f"{invention.invention_no} · 작성 {invention.created_at.strftime('%Y-%m-%d')}"
        f" · 수정 {invention.updated_at.strftime('%Y-%m-%d')}"
    )

    cols = st.columns(3)
    if cols[0].button(
        "⭐ 즐겨찾기 해제" if invention.is_favorite else "☆ 즐겨찾기",
        key=f"fav_{invention.id}",
    ):
        run_and_rerun(
            lambda session: InventionService(session).toggle_favorite(invention.id)
        )

    current_status = (
        STATUS_VALUES.index(invention.status)
        if invention.status in STATUS_VALUES
        else 0
    )
    new_status = cols[1].selectbox(
        "상태", STATUS_VALUES, index=current_status, key=f"status_{invention.id}"
    )
    if new_status != invention.status:
        run_and_rerun(
            lambda session: InventionService(session).update_fields(
                invention.id, status=new_status
            )
        )

    if cols[2].button("← 홈으로", key=f"back_{invention.id}"):
        go("home")

    with get_session() as session:
        tag_names = InventionService(session).tags.tag_names(invention.id)
    tags_text = st.text_input(
        "태그 (쉼표로 구분)",
        value=", ".join(tag_names),
        key=f"tags_{invention.id}",
    )
    if st.button("태그 저장", key=f"tags_save_{invention.id}"):
        names = [t.strip() for t in tags_text.split(",") if t.strip()]
        run_and_rerun(
            lambda session: InventionService(session).set_tags(invention.id, names)
        )


def _render_original(invention) -> None:
    st.subheader("원본 아이디어")
    st.caption("처음 적어둔 내용입니다. 고쳐도 이전 내용은 변경 이력에 남습니다.")
    st.info(invention.original_idea)

    with st.expander("원본 내용 고치기", expanded=False):
        edited = st.text_area(
            "원본 아이디어",
            value=invention.original_idea,
            height=180,
            key=f"orig_edit_{invention.id}",
            label_visibility="collapsed",
        )
        if st.button("원본 저장", key=f"orig_save_{invention.id}"):
            errors = []
            if not edited or not edited.strip():
                errors.append("아이디어 내용을 입력하세요.")
            if errors:
                for message in errors:
                    st.error(message)
            else:
                run_and_rerun(
                    lambda session: InventionService(session).update_original_idea(
                        invention.id, edited
                    )
                )


def _render_filled_sections(invention) -> None:
    filled = [
        (name, FIELD_LABELS[name][0], (getattr(invention, name) or "").strip())
        for _, _, fields in DETAIL_GROUPS
        for name in fields
        if (getattr(invention, name) or "").strip()
    ]
    if not filled:
        return

    st.subheader("정리한 내용")
    for _, label, value in filled:
        with st.container(border=True):
            st.markdown(f"**{label}**")
            st.write(value)


def _render_group_editors(invention) -> None:
    st.subheader("내용 채우기")
    st.caption("필요한 것만 눌러서 채우세요. 한 번에 다 적지 않아도 됩니다.")

    for group_name, description, fields in DETAIL_GROUPS:
        has_content = any((getattr(invention, f) or "").strip() for f in fields)
        label = f"{group_name}{' ✓' if has_content else ''}"
        with st.expander(label, expanded=False):
            st.caption(description)
            with st.form(f"group_{invention.id}_{group_name}"):
                values: dict[str, str] = {}
                for name in fields:
                    field_label, help_text = FIELD_LABELS[name]
                    values[name] = st.text_area(
                        field_label,
                        value=getattr(invention, name) or "",
                        help=help_text or None,
                        height=130,
                        key=f"f_{invention.id}_{name}",
                    )
                saved = st.form_submit_button("저장")
            if saved:
                payload = {k: (v or None) for k, v in values.items()}
                run_and_rerun(
                    lambda session: InventionService(session).update_fields(
                        invention.id, **payload
                    )
                )


def _run_ai_review(invention_id: str, kind: str, label: str) -> None:
    """AI 검토 버튼 하나의 실행 흐름.

    AI 호출은 DB 쓰기 세션 밖에서 하고(실패해도 발명 내용에 영향 없음),
    성공했을 때만 결과를 InventionAIResult로 저장한다 — 저장 자체는 짧은
    트랜잭션 하나(run_and_rerun)라 실패하면 부분 저장 없이 전부 롤백된다.
    """
    processing_key = f"ai_review_running_{invention_id}"
    if st.session_state.get(processing_key):
        st.warning("이미 처리 중입니다. 잠시만 기다려 주세요.")
        return

    st.session_state[processing_key] = True
    try:
        settings = get_settings()
        provider, warning = get_ai_provider(settings)
        if warning:
            st.info(warning)
        with st.spinner(f"{label} 실행 중..."):
            with get_session() as read_session:
                fresh = InventionService(read_session).get(invention_id)
                context = build_context(fresh)
                content = provider.review_invention(fresh, kind)
        model_name = getattr(provider, "model", None)
        run_and_rerun(
            lambda session, k=kind, c=content, ctx=context, pname=provider.name, m=model_name: (
                AIResultService(session).create_draft(
                    invention_id, k, c, provider=pname, model=m, input_snapshot=ctx
                )
            )
        )
    except AIProviderError as exc:
        st.error(f"{label} 실행에 실패했습니다.\n\n{exc}\n\n발명 내용은 변경되지 않았습니다.")
    finally:
        st.session_state[processing_key] = False


def _render_ai_review(invention) -> None:
    with st.expander("🤖 AI로 검토하기", expanded=False):
        st.caption(
            "버튼을 누르면 AI가 참고용 초안을 만듭니다. 아래 'AI 검토 결과'에서 "
            "직접 반영을 눌러야만 발명 내용이 바뀝니다."
        )
        for group_name, items in REVIEW_GROUPS:
            st.markdown(f"**{group_name}**")
            cols = st.columns(2)
            for i, (kind, label) in enumerate(items):
                if cols[i % 2].button(label, key=f"ai_review_{kind}_{invention.id}"):
                    _run_ai_review(invention.id, kind, label)


def _render_ai_results(invention) -> None:
    with get_session() as session:
        results = AIResultService(session).list_for_invention(invention.id)

    if not results:
        return

    # 오래된 것부터 번호를 매겨 같은 종류를 "1차/2차..."로 구분한다.
    ordinal: dict[str, int] = {}
    counters: dict[str, int] = {}
    for r in reversed(results):
        counters[r.kind] = counters.get(r.kind, 0) + 1
        ordinal[r.id] = counters[r.kind]

    pending_count = sum(1 for r in results if r.status == "생성됨")
    with st.expander(f"AI 검토 결과 ({len(results)}건, 대기 {pending_count}건)", expanded=pending_count > 0):
        for r in results:
            label = RESULT_KINDS.get(r.kind, r.kind)
            status_badge = {"반영됨": " · ✅ 반영됨", "보관됨": " · 📦 보관됨"}.get(r.status, "")
            with st.container(border=True):
                st.markdown(f"**{label} {ordinal[r.id]}차**{status_badge}")
                meta = r.created_at.strftime("%Y-%m-%d %H:%M") + f" · {r.provider}"
                if r.model:
                    meta += f"/{r.model}"
                st.caption(meta)
                st.write(r.content)

                if r.status == "생성됨":
                    action_cols = st.columns(2)
                    if action_cols[0].button("전체 반영", key=f"apply_all_{r.id}"):
                        run_and_rerun(
                            lambda session, rid=r.id: AIResultService(session).apply(rid)
                        )
                    if action_cols[1].button("보관", key=f"archive_{r.id}"):
                        run_and_rerun(
                            lambda session, rid=r.id: AIResultService(session).archive(rid)
                        )

                    with st.expander("일부만 반영", expanded=False):
                        default_field = REVIEW_DEFAULT_FIELD.get(r.kind)
                        field_keys = [f for f, _ in PARTIAL_APPLY_FIELDS]
                        chosen = st.multiselect(
                            "반영할 항목 선택",
                            options=field_keys,
                            default=[default_field] if default_field in field_keys else [],
                            format_func=lambda f: PARTIAL_APPLY_FIELD_LABELS.get(f, f),
                            key=f"partial_fields_{r.id}",
                        )
                        if st.button("선택한 항목에 반영", key=f"apply_partial_{r.id}"):
                            if not chosen:
                                st.warning("반영할 항목을 하나 이상 선택하세요.")
                            else:
                                run_and_rerun(
                                    lambda session, rid=r.id, fields=chosen: AIResultService(
                                        session
                                    ).apply(rid, target_fields=fields)
                                )

                    redo_cols = st.columns(2)
                    if redo_cols[0].button("다시 생성", key=f"redo_{r.id}"):
                        _run_ai_review(invention.id, r.kind, label)
                    if redo_cols[1].button("삭제", key=f"discard_{r.id}"):
                        run_and_rerun(
                            lambda session, rid=r.id: AIResultService(session).discard(rid)
                        )
                elif r.applied_fields:
                    applied_labels = ", ".join(
                        PARTIAL_APPLY_FIELD_LABELS.get(f, f) for f in r.applied_fields
                    )
                    st.caption(f"반영된 항목: {applied_labels}")


def _render_related_ideas(invention) -> None:
    with get_session() as session:
        service = InventionService(session)
        parent = service.get(invention.parent_invention_id) if invention.parent_invention_id else None
        children = service.list_children(invention.id)

    label = "관련 아이디어"
    if children:
        label += f" (파생 {len(children)}건)"
    with st.expander(label, expanded=False):
        st.caption("부모/파생 아이디어를 카드로 보여줍니다.")

        if st.button("🌱 이 발명에서 파생 아이디어 만들기", key=f"derive_from_detail_{invention.id}"):
            start_derive_capture(invention.id, invention.invention_no, invention.title)

        if invention.derivation_reason:
            st.caption(f"이 발명의 파생 이유: {invention.derivation_reason}")

        if parent is not None:
            st.markdown("**부모 발명**")
            with st.container(border=True):
                st.markdown(f"{parent.invention_no} · {parent.title}")
                st.caption(f"상태: {parent.status}")
                if st.button("부모 발명 열기", key=f"open_parent_{invention.id}"):
                    go("detail", parent.id)

        if children:
            st.markdown(f"**파생 발명 ({len(children)}건)**")
            for child in children:
                with st.container(border=True):
                    st.markdown(f"{child.invention_no} · {child.title}")
                    meta = f"상태: {child.status} · 생성 {child.created_at.strftime('%Y-%m-%d')}"
                    if child.derivation_reason:
                        meta += f" · 파생 이유: {child.derivation_reason}"
                    st.caption(meta)
                    if st.button("열기", key=f"open_child_{child.id}"):
                        go("detail", child.id)

        if parent is None and not children:
            st.caption("아직 연결된 부모/파생 발명이 없습니다.")


def _render_experiments(invention) -> None:
    with get_session() as session:
        experiments = ExperimentService(session).list_for_invention(invention.id)

    with st.expander(f"실험 기록 ({len(experiments)}건)", expanded=False):
        st.caption("실험 날짜/조건/결과/실패 원인/개선 아이디어를 따로 남깁니다.")
        with st.form(f"experiment_new_{invention.id}"):
            has_date = st.checkbox("날짜 입력", value=True, key=f"exp_has_date_{invention.id}")
            exp_date = (
                st.date_input("실험 날짜", value=date.today(), key=f"exp_date_{invention.id}")
                if has_date
                else None
            )
            conditions = st.text_area("조건", key=f"exp_cond_{invention.id}")
            results = st.text_area("결과", key=f"exp_result_{invention.id}")
            failure_reason = st.text_area("실패 원인 (있다면)", key=f"exp_fail_{invention.id}")
            improvement_ideas = st.text_area(
                "개선 아이디어", key=f"exp_improve_{invention.id}"
            )
            submitted = st.form_submit_button("실험 기록 추가")

        if submitted:
            data = ExperimentInput(
                experiment_date=exp_date,
                conditions=conditions or None,
                results=results or None,
                failure_reason=failure_reason or None,
                improvement_ideas=improvement_ideas or None,
            )
            errors = data.validate()
            if errors:
                for message in errors:
                    st.error(message)
            else:
                run_and_rerun(
                    lambda session: ExperimentService(session).create(invention.id, data)
                )

        for exp in experiments:
            date_label = exp.experiment_date.isoformat() if exp.experiment_date else "날짜 미상"
            with st.container(border=True):
                st.markdown(f"**{date_label}**")
                if exp.conditions:
                    st.markdown(f"- 조건: {exp.conditions}")
                if exp.results:
                    st.markdown(f"- 결과: {exp.results}")
                if exp.failure_reason:
                    st.markdown(f"- 실패 원인: {exp.failure_reason}")
                if exp.improvement_ideas:
                    st.markdown(f"- 개선 아이디어: {exp.improvement_ideas}")
                exp_cols = st.columns(2)
                if exp_cols[0].button("🌱 이 실험 결과로 파생 아이디어 만들기", key=f"exp_derive_{exp.id}"):
                    # start_derive_capture()는 끝에서 st.rerun()을 호출해 실행을
                    # 즉시 끊으므로, 초안 메모는 반드시 그 전에 심어 둬야 한다.
                    st.session_state["capture_memo"] = draft_text_from_experiment(exp)
                    start_derive_capture(
                        invention.id,
                        invention.invention_no,
                        invention.title,
                        source_experiment_id=exp.id,
                    )
                if exp_cols[1].button("삭제", key=f"exp_del_{exp.id}"):
                    run_and_rerun(
                        lambda session, exp_id=exp.id: ExperimentService(session).delete(
                            exp_id
                        )
                    )


def _render_attachments(invention) -> None:
    with get_session() as session:
        attachments = AttachmentService(session).list_for_invention(invention.id)

    with st.expander(f"사진·파일 ({len(attachments)}건)", expanded=False):
        uploaded = st.file_uploader(
            "파일 추가",
            type=["png", "jpg", "jpeg", "pdf", "wav", "mp3", "m4a", "ogg", "webm", "mp4", "mov"],
            accept_multiple_files=True,
            key=f"att_up_{invention.id}",
        )
        photo = st.camera_input("사진 찍기", key=f"att_cam_{invention.id}")
        voice = st.audio_input("음성 메모", key=f"att_voice_{invention.id}")
        category = st.selectbox(
            "종류", ATTACHMENT_CATEGORIES, key=f"att_category_{invention.id}"
        )

        if st.button("첨부 저장", key=f"att_save_{invention.id}"):
            items = [item for item in (photo, voice, *list(uploaded or [])) if item]
            if not items:
                st.warning("첨부할 파일을 먼저 선택하세요.")
            else:
                problems: list[str] = []

                def _save_all(session, items=items, problems=problems, category=category):
                    service = AttachmentService(session)
                    for item in items:
                        name = getattr(item, "name", None) or "voice-memo.wav"
                        try:
                            service.save(
                                invention.id,
                                name,
                                item.getvalue(),
                                content_type=getattr(item, "type", None),
                                category=category,
                            )
                        except AttachmentError as exc:
                            problems.append(f"{name}: {exc}")

                run_and_rerun(_save_all)

        for att in attachments:
            kind = attachment_kind(att.original_filename)
            with get_session() as session:
                path = AttachmentService(session).resolve_path(att)
            st.markdown(f"**{att.original_filename}** · {att.category}")
            if path.exists():
                if kind == "image":
                    st.image(str(path), width=320)
                elif kind == "audio":
                    st.audio(str(path))
                elif kind == "video":
                    st.video(str(path))
            if st.button("삭제", key=f"att_del_{att.id}"):
                run_and_rerun(
                    lambda session, att_id=att.id: AttachmentService(
                        session
                    ).delete_by_id(att_id)
                )


def _render_timeline(invention) -> None:
    with get_session() as session:
        events = InventionService(session).list_timeline(invention.id)

    with st.expander(f"Timeline ({len(events)}건)", expanded=False):
        st.caption("이 발명이 시간이 지나며 어떻게 발전했는지 자동으로 기록됩니다.")
        if not events:
            st.caption("아직 기록된 사건이 없습니다.")
            return

        for event in events:
            line = f"**{event.occurred_at.strftime('%Y-%m-%d %H:%M')}** · {event.title}"
            if event.description:
                line += f" — {event.description}"
            st.markdown(line)


def _render_history(invention) -> None:
    with get_session() as session:
        revisions = InventionService(session).list_revisions(invention.id)

    with st.expander(f"변경 이력 ({len(revisions)}건)", expanded=False):
        note = st.text_input("메모", key=f"rev_note_{invention.id}")
        if st.button("현재 내용을 버전으로 저장", key=f"rev_save_{invention.id}"):
            run_and_rerun(
                lambda session: InventionService(session).save_revision(
                    invention.id, change_note=note or None
                )
            )

        if not revisions:
            st.caption("아직 저장된 이전 버전이 없습니다.")
            return

        for rev in revisions:
            st.markdown(
                f"**v{rev.revision_no}** · {rev.created_at.strftime('%Y-%m-%d %H:%M')}"
                f" · {rev.change_note or '메모 없음'}"
            )
            snapshot_original = (rev.snapshot_json or {}).get("original_idea", "")
            if snapshot_original:
                st.caption("그때의 원본 아이디어")
                st.text(snapshot_original)


def _render_export(invention) -> None:
    with st.expander("내보내기", expanded=False):
        markdown = export_invention_markdown(invention, list(invention.patent_links))
        st.download_button(
            "Markdown 파일로 저장",
            data=markdown.encode("utf-8"),
            file_name=f"{invention.invention_no}.md",
            mime="text/markdown",
            key=f"md_{invention.id}",
        )


def _render_danger_zone(invention) -> None:
    with st.expander("보관 / 삭제", expanded=False):
        if st.button(
            "보관 해제" if invention.is_archived else "보관하기",
            key=f"arch_{invention.id}",
        ):
            run_and_rerun(
                lambda session: InventionService(session).set_archived(
                    invention.id, not invention.is_archived
                )
            )

        confirm_key = f"confirm_del_{invention.id}"
        if st.button("삭제", key=f"del_{invention.id}"):
            st.session_state[confirm_key] = True

        if st.session_state.get(confirm_key):
            st.warning(f"'{invention.title}'을(를) 삭제합니다. 되돌릴 수 없습니다.")
            cols = st.columns(2)
            if cols[0].button("삭제 확정", key=f"del_ok_{invention.id}"):
                with get_session() as session:
                    InventionService(session).delete(invention.id)
                st.session_state.pop(confirm_key, None)
                DraftStore().clear(f"detail_{invention.id}")
                go("home")
            if cols[1].button("취소", key=f"del_no_{invention.id}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()


def render(invention_id: str | None) -> None:
    if not invention_id:
        st.info("먼저 아이디어를 선택하거나 새로 기록하세요.")
        if st.button("새 아이디어 기록", key="detail_to_capture"):
            clear_derive_context()
            go("capture")
        return

    with get_session() as session:
        invention = InventionService(session).get(invention_id)
        if invention is None:
            st.error("해당 아이디어를 찾을 수 없습니다.")
            if st.button("홈으로", key="detail_missing_home"):
                go("home")
            return

        _render_header(invention)
        st.divider()
        _render_original(invention)
        _render_filled_sections(invention)
        st.divider()
        _render_group_editors(invention)
        st.divider()
        _render_ai_review(invention)
        _render_ai_results(invention)
        _render_related_ideas(invention)
        st.divider()
        _render_experiments(invention)
        _render_attachments(invention)

        with st.expander("비슷한 기술 찾아보기", expanded=False):
            st.caption(
                "이미 나와 있는 비슷한 기술(선행특허)을 찾아 내 아이디어와 비교해 둡니다."
            )
            from src.ui.pages import patent_search

            patent_search.render(invention.id)

        _render_timeline(invention)
        _render_history(invention)
        _render_export(invention)
        _render_danger_zone(invention)
