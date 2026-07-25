"""빠른 아이디어 기록 화면.

필수 입력은 아이디어 내용 하나뿐이다. 제목·태그·첨부는 모두 선택이며
접어둔다. 목표는 '열자마자 쓰고 바로 저장'이다.
"""
from __future__ import annotations

import streamlit as st

from src.attachments.service import AttachmentError, AttachmentService
from src.database.engine import get_session
from src.drafts.store import DraftStore
from src.inventions.schemas import QuickIdeaInput
from src.inventions.service import InventionService
from src.ui.components.layout import go

_DRAFT_KEY = "quick_capture"
_MEMO_WIDGET = "capture_memo"


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

    st.title("새 아이디어")
    st.caption("생각나는 대로 적어두세요. 제목과 정리는 나중에 해도 됩니다.")

    # 이전에 쓰다 만 내용이 있으면 되살린다.
    if _MEMO_WIDGET not in st.session_state:
        st.session_state[_MEMO_WIDGET] = draft_store.get(_DRAFT_KEY)

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
        title = st.text_input(
            "제목", key="capture_title", placeholder="비워두면 자동으로 만들어집니다"
        )
        tags_text = st.text_input(
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
            invention = InventionService(session).quick_create(data)
            uploads = [photo, voice] + list(files or [])
            problems = _save_attachments(session, invention.id, uploads)
            invention_id = invention.id

        # 저장에 성공했으므로 임시 보관분을 정리한다.
        draft_store.clear(_DRAFT_KEY)
        for widget in (_MEMO_WIDGET, "capture_title", "capture_tags"):
            st.session_state.pop(widget, None)

        if problems:
            st.warning("일부 첨부파일을 저장하지 못했습니다: " + " / ".join(problems))
        go("detail", invention_id)

    if st.button("취소", key="capture_cancel"):
        go("home")
