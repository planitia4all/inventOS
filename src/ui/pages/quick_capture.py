"""빠른 아이디어 기록 화면.

필수 입력은 아이디어 내용 하나뿐이다. 제목·태그·첨부는 모두 선택이며
접어둔다. 목표는 '열자마자 쓰고 바로 저장'이다.
"""
from __future__ import annotations

import streamlit as st

from src.attachments.service import AttachmentError, AttachmentService
from src.database.engine import get_session
from src.drafts.store import DraftStore
from src.inventions.schemas import DERIVATION_COPY_FIELDS, DERIVATION_REASONS, QuickIdeaInput
from src.inventions.service import InventionService
from src.ui.components.layout import go

_DRAFT_KEY = "quick_capture"
_MEMO_WIDGET = "capture_memo"

# 파생 아이디어 모드로 캡처 화면에 들어왔을 때만 쓰는 session_state 키.
_DERIVE_KEYS = (
    "derive_parent_id",
    "derive_parent_no",
    "derive_parent_title",
    "derive_source_experiment_id",
    "derive_memo_prefilled",
)


def clear_derive_context() -> None:
    """파생 모드가 아닌 '새 아이디어 기록' 진입점에서 반드시 호출해야 한다.

    안 그러면 이전에 시작했다가 끝내지 않은 파생 흐름의 배너/체크박스가
    엉뚱하게 새 기록 화면에 남아 있게 된다.
    """
    for key in _DERIVE_KEYS:
        st.session_state.pop(key, None)


def start_derive_capture(
    parent_id: str,
    parent_no: str,
    parent_title: str,
    source_experiment_id: str | None = None,
) -> None:
    """상세 화면의 '파생 아이디어 만들기' 버튼이 호출한다."""
    st.session_state["derive_parent_id"] = parent_id
    st.session_state["derive_parent_no"] = parent_no
    st.session_state["derive_parent_title"] = parent_title
    st.session_state["derive_source_experiment_id"] = source_experiment_id
    st.session_state.pop("derive_memo_prefilled", None)
    st.session_state.page = "capture"
    st.session_state.current_invention_id = None
    st.rerun()


def _keywords_from_text(text: str) -> list[str]:
    return [k.strip() for k in (text or "").replace("\n", ",").split(",") if k.strip()]


def persist_pending_draft() -> None:
    """쓰다 만 내용을 임시 저장한다.

    app.py가 매 실행마다 가장 먼저 호출한다. 상단 이동 버튼은 화면 본문보다
    먼저 처리되기 때문에, 여기서 저장해두지 않으면 글을 쓰다가 다른 화면으로
    이동하는 순간 내용이 사라진다.
    """
    if _MEMO_WIDGET not in st.session_state:
        return

    text = st.session_state.get(_MEMO_WIDGET) or ""
    store = DraftStore()
    if text != store.get(_DRAFT_KEY):
        store.save(_DRAFT_KEY, text)


def _save_attachments(session, invention_id: str, uploads) -> list[str]:
    """첨부 저장. 실패한 파일은 메시지로 모아서 돌려주고 저장 자체는 막지 않는다."""
    service = AttachmentService(session)
    problems: list[str] = []
    for item in uploads:
        if item is None:
            continue
        name = getattr(item, "name", None) or "voice-memo.wav"
        try:
            service.save(
                invention_id,
                name,
                item.getvalue(),
                content_type=getattr(item, "type", None),
            )
        except AttachmentError as exc:
            problems.append(f"{name}: {exc}")
    return problems


def render() -> None:
    draft_store = DraftStore()

    parent_id = st.session_state.get("derive_parent_id")
    parent_no = st.session_state.get("derive_parent_no")
    parent_title = st.session_state.get("derive_parent_title")
    source_experiment_id = st.session_state.get("derive_source_experiment_id")
    is_derive_mode = bool(parent_id)

    st.title("파생 아이디어 만들기" if is_derive_mode else "새 아이디어")
    if is_derive_mode:
        st.info(f"🌱 '{parent_title}'({parent_no})에서 파생되는 아이디어입니다.")
    else:
        st.caption("생각나는 대로 적어두세요. 제목과 정리는 나중에 해도 됩니다.")

    # 이전에 쓰다 만 내용이 있으면 되살린다.
    if _MEMO_WIDGET not in st.session_state:
        st.session_state[_MEMO_WIDGET] = draft_store.get(_DRAFT_KEY)

    copy_fields: list[str] = []
    copy_tags = False
    copy_attachments = False
    derivation_reason: str | None = None

    if is_derive_mode:
        with st.expander("부모 발명에서 가져올 내용 (선택)", expanded=True):
            st.caption("기본값은 관계만 연결합니다. 필요한 것만 골라서 가져오세요.")
            copy_memo = st.checkbox("원본 메모 가져오기", key="derive_copy_memo")
            if copy_memo and not st.session_state.get("derive_memo_prefilled"):
                with get_session() as session:
                    parent = InventionService(session).get(parent_id)
                    if parent is not None:
                        st.session_state[_MEMO_WIDGET] = parent.original_idea
                st.session_state["derive_memo_prefilled"] = True
            elif not copy_memo:
                st.session_state["derive_memo_prefilled"] = False

            for field_label, field_name in DERIVATION_COPY_FIELDS:
                if st.checkbox(f"{field_label} 가져오기", key=f"derive_copy_{field_name}"):
                    copy_fields.append(field_name)
            copy_tags = st.checkbox("태그 가져오기", key="derive_copy_tags")
            copy_attachments = st.checkbox("첨부파일 가져오기", key="derive_copy_attachments")

            reason_choice = st.selectbox(
                "파생 이유", DERIVATION_REASONS, key="derive_reason_choice"
            )
            if reason_choice == "기타":
                custom_reason = st.text_input("파생 이유 (직접 입력)", key="derive_reason_custom")
                derivation_reason = custom_reason.strip() or "기타"
            else:
                derivation_reason = reason_choice

    memo = st.text_area(
        "아이디어 내용",
        key=_MEMO_WIDGET,
        height=220,
        placeholder="예) 금속 핀을 먼저 배열하고 그 주변에 유리를 성형하면 비아 홀 가공 없이 관통전극을 만들 수 있지 않을까?",
    )

    # 입력이 확정될 때마다(입력창을 벗어나거나 버튼을 누를 때) 임시 저장한다.
    # 브라우저를 새로고침해도 남는다.
    if memo != draft_store.get(_DRAFT_KEY):
        draft_store.save(_DRAFT_KEY, memo)
    if memo.strip():
        st.caption("작성 중인 내용은 자동으로 임시 저장됩니다.")

    with st.expander("제목·태그 (선택)", expanded=False):
        # 값은 위젯 key(capture_title/capture_tags)를 통해 session_state에서
        # 바로 읽으므로(저장 버튼 핸들러 참고) 반환값을 따로 저장할 필요는 없다.
        st.text_input(
            "제목", key="capture_title", placeholder="비워두면 자동으로 만들어집니다"
        )
        st.text_input(
            "태그", key="capture_tags", placeholder="쉼표로 구분 (예: 유리기판, 관통전극)"
        )

    with st.expander("사진·파일·음성 (선택)", expanded=False):
        photo = st.camera_input("사진 찍기", key="capture_camera")
        files = st.file_uploader(
            "파일 첨부",
            type=["png", "jpg", "jpeg", "pdf"],
            accept_multiple_files=True,
            key="capture_files",
        )
        voice = st.audio_input("음성 메모", key="capture_voice")

    if st.button("저장", type="primary", key="capture_save"):
        data = QuickIdeaInput(
            memo=memo,
            title=st.session_state.get("capture_title", ""),
            keywords=_keywords_from_text(st.session_state.get("capture_tags", "")),
        )
        errors = data.validate()
        if errors:
            for message in errors:
                st.error(message)
            return

        with get_session() as session:
            if is_derive_mode:
                invention = InventionService(session).create_child(
                    parent_id,
                    data,
                    derivation_reason=derivation_reason,
                    copy_fields=copy_fields,
                    copy_tags=copy_tags,
                    copy_attachments=copy_attachments,
                    source_experiment_id=source_experiment_id,
                )
            else:
                invention = InventionService(session).quick_create(data)
            uploads = [photo, voice] + list(files or [])
            problems = _save_attachments(session, invention.id, uploads)
            invention_id = invention.id

        # 저장에 성공했으므로 임시 보관분을 정리한다.
        draft_store.clear(_DRAFT_KEY)
        for widget in (_MEMO_WIDGET, "capture_title", "capture_tags"):
            st.session_state.pop(widget, None)
        clear_derive_context()

        if problems:
            st.warning("일부 첨부파일을 저장하지 못했습니다: " + " / ".join(problems))
        go("detail", invention_id)

    if st.button("취소", key="capture_cancel"):
        clear_derive_context()
        go("home")
