"""첨부파일 저장 서비스.

바이너리는 DB가 아니라 data/attachments/<invention_id>/ 폴더에 저장하고,
DB에는 경로와 원본 파일명만 기록한다. 종류(category)를 함께 남겨서
나중에 "사진만", "실험 자료만" 처럼 찾기 쉽게 한다.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
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

# 로컬 단일 사용자 프로그램이라도 실수로 아주 큰 파일(예: 편집 안 된 원본
# 동영상)을 올려서 디스크를 가득 채우는 것은 막아 둔다.
MAX_ATTACHMENT_SIZE_BYTES = 200 * 1024 * 1024  # 200MB

_DEFAULT_CATEGORY_BY_EXTENSION: dict[str, str] = {
    **{ext: "사진" for ext in IMAGE_EXTENSIONS},
    **{ext: "음성" for ext in AUDIO_EXTENSIONS},
    **{ext: "동영상" for ext in VIDEO_EXTENSIONS},
    ".pdf": "참고자료",
}


class AttachmentError(Exception):
    pass


@dataclass
class AttachmentIntegrityReport:
    """설정 화면 '첨부파일 무결성 검사'용 점검 결과.

    실제로 삭제하는 동작은 없다 — 자동 삭제는 위험해서, 이 단계에서는
    사용자에게 무엇이 문제인지 보여주기만 한다.
    """

    missing_files: list[dict] = field(default_factory=list)  # DB 행은 있는데 실제 파일이 없음
    orphaned_files: list[str] = field(default_factory=list)  # 파일은 있는데 DB 행이 없음
    zero_byte_files: list[dict] = field(default_factory=list)  # 파일은 있는데 크기가 0
    duplicate_groups: list[list[dict]] = field(default_factory=list)  # 내용이 완전히 같은 파일들

    @property
    def is_healthy(self) -> bool:
        return not (
            self.missing_files or self.orphaned_files or self.zero_byte_files
            or self.duplicate_groups
        )


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
        if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
            limit_mb = MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)
            raise AttachmentError(
                f"파일이 너무 큽니다 (최대 {limit_mb}MB). "
                "동영상은 압축한 뒤 다시 시도하세요."
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

    def copy_to_invention(self, attachment: Attachment, target_invention_id: str) -> Attachment:
        """첨부파일 실물을 복사해 다른 발명(주로 파생 아이디어)에 붙인다.

        기존 `save()`를 그대로 재사용한다 — 파일을 먼저 쓰고 성공했을 때만
        DB 행을 만들기 때문에, 복사 도중 실패해도 파일 없는 DB 행이나 DB
        행 없는 파일이 새로 생기지 않는다.
        """
        source_path = self.resolve_path(attachment)
        content = source_path.read_bytes()
        return self.save(
            target_invention_id,
            attachment.original_filename,
            content,
            content_type=attachment.content_type,
            category=attachment.category,
        )

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
        original_filename = attachment.original_filename
        self.session.delete(attachment)
        self.session.flush()
        TimelineService(self.session).log(
            invention_id, "attachment_removed", description=original_filename
        )
        SearchIndexService(self.session).reindex_invention(invention_id)

    def delete_by_id(self, attachment_id: str) -> None:
        """다른 세션에서 조회한 첨부(detached 객체) 대신 id로 안전하게 삭제한다."""
        attachment = self.session.get(Attachment, attachment_id)
        if attachment is not None:
            self.delete(attachment)

    def check_integrity(self) -> AttachmentIntegrityReport:
        """DB 기록과 실제 파일이 서로 어긋난 곳이 있는지 점검한다.

        파일 복사 성공 후 DB 저장 실패, DB 삭제 성공 후 파일 삭제 실패
        같은 상황이 남긴 흔적(고아 파일/깨진 DB 행)을 찾아낸다. 찾기만
        하고 지우지는 않는다 — 삭제는 사용자가 결과를 보고 직접 판단할 일이다.
        """
        report = AttachmentIntegrityReport()
        attachments = list(self.session.query(Attachment).order_by(Attachment.uploaded_at))

        referenced_paths: set[Path] = set()
        hashes: dict[str, list[dict]] = {}

        for attachment in attachments:
            path = self.resolve_path(attachment)
            info = {
                "id": attachment.id,
                "invention_id": attachment.invention_id,
                "original_filename": attachment.original_filename,
                "stored_path": attachment.stored_path,
            }
            if not path.exists():
                report.missing_files.append(info)
                continue

            referenced_paths.add(path.resolve())
            size = path.stat().st_size
            if size == 0:
                report.zero_byte_files.append(info)
                continue

            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes.setdefault(digest, []).append(info)

        for group in hashes.values():
            if len(group) > 1:
                report.duplicate_groups.append(group)

        attachments_dir = self.settings.attachments_dir
        if attachments_dir.exists():
            for path in attachments_dir.rglob("*"):
                if path.is_file() and path.resolve() not in referenced_paths:
                    report.orphaned_files.append(
                        str(path.relative_to(self.settings.data_dir))
                    )

        return report


__all__ = [
    "ATTACHMENT_CATEGORIES",
    "AttachmentError",
    "AttachmentIntegrityReport",
    "AttachmentService",
    "attachment_kind",
    "default_category",
]
