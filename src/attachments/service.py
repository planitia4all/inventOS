"""첨부파일 저장 서비스.

바이너리는 DB가 아니라 data/attachments/<invention_id>/ 폴더에 저장하고,
DB에는 경로와 원본 파일명만 기록한다. 종류(category)를 함께 남겨서
나중에 "사진만", "실험 자료만" 처럼 찾기 쉽게 한다.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.config.settings import Settings, get_settings
from src.database.models import ATTACHMENT_CATEGORIES, Attachment
from src.search.fts import SearchIndexService
from src.timeline.service import TimelineService

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
DOCUMENT_EXTENSIONS = {".pdf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

_DEFAULT_CATEGORY_BY_EXTENSION: dict[str, str] = {
    **{ext: "사진" for ext in IMAGE_EXTENSIONS},
    **{ext: "음성" for ext in AUDIO_EXTENSIONS},
    **{ext: "동영상" for ext in VIDEO_EXTENSIONS},
    ".pdf": "참고자료",
}


class AttachmentError(Exception):
    pass


def attachment_kind(filename: str) -> str:
    """UI가 미리보기 방식을 고르기 위한 분류: image | audio | video | document | other."""
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "other"


def default_category(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return _DEFAULT_CATEGORY_BY_EXTENSION.get(ext, "기타")


class AttachmentService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    def save(
        self,
        invention_id: str,
        original_filename: str,
        content: bytes,
        content_type: str | None = None,
        category: str | None = None,
        experiment_id: str | None = None,
    ) -> Attachment:
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AttachmentError(
                f"허용되지 않은 파일 형식입니다: {ext} "
                "(사진 PNG/JPG, 문서 PDF, 음성 WAV/MP3/M4A/OGG/WEBM, "
                "동영상 MP4/MOV만 가능)"
            )

        target_dir = self.settings.attachments_dir / invention_id
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            stored_name = f"{uuid.uuid4()}{ext}"
            target_path = target_dir / stored_name
            target_path.write_bytes(content)
        except OSError as exc:
            raise AttachmentError(f"첨부파일 저장에 실패했습니다: {exc}") from exc

        attachment = Attachment(
            invention_id=invention_id,
            experiment_id=experiment_id,
            original_filename=original_filename,
            stored_path=str(target_path.relative_to(self.settings.data_dir)),
            content_type=content_type,
            category=category or default_category(original_filename),
        )
        self.session.add(attachment)
        self.session.flush()
        TimelineService(self.session).log(
            invention_id, "attachment_added", description=original_filename
        )
        SearchIndexService(self.session).reindex_invention(invention_id)
        return attachment

    def list_for_invention(self, invention_id: str) -> list[Attachment]:
        return list(
            self.session.query(Attachment)
            .filter(Attachment.invention_id == invention_id)
            .order_by(Attachment.uploaded_at.desc())
        )

    def list_for_experiment(self, experiment_id: str) -> list[Attachment]:
        return list(
            self.session.query(Attachment)
            .filter(Attachment.experiment_id == experiment_id)
            .order_by(Attachment.uploaded_at.desc())
        )

    def resolve_path(self, attachment: Attachment) -> Path:
        return self.settings.data_dir / attachment.stored_path

    def delete(self, attachment: Attachment) -> None:
        path = self.resolve_path(attachment)
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        invention_id = attachment.invention_id
        self.session.delete(attachment)
        self.session.flush()
        SearchIndexService(self.session).reindex_invention(invention_id)

    def delete_by_id(self, attachment_id: str) -> None:
        """다른 세션에서 조회한 첨부(detached 객체) 대신 id로 안전하게 삭제한다."""
        attachment = self.session.get(Attachment, attachment_id)
        if attachment is not None:
            self.delete(attachment)


__all__ = [
    "ATTACHMENT_CATEGORIES",
    "AttachmentError",
    "AttachmentService",
    "attachment_kind",
    "default_category",
]
