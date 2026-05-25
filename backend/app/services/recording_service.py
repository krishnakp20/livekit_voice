"""Call recording storage and lookup."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.recording import Recording


def recordings_root() -> Path:
    raw = Path(settings.RECORDINGS_PATH)
    path = raw if raw.is_absolute() else Path(__file__).resolve().parents[2] / raw
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_room_basename(room_name: str) -> str:
    return room_name.replace("/", "_").replace("\\", "_").replace(":", "_")


def resolve_recording_path(room_name: str, stored_path: str | None = None) -> Path | None:
    """Find recording file on disk (DB path or standard room filename)."""
    candidates: list[Path] = []
    if stored_path:
        candidates.append(Path(stored_path))
    candidates.append(recording_path_for_room(room_name))
    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


def recording_path_for_room(room_name: str) -> Path:
    """Preferred local path for API playback (also checks egress output mount)."""
    name = f"{safe_room_basename(room_name)}.ogg"
    if settings.LIVEKIT_EGRESS_OUTPUT_DIR:
        egress_file = Path(settings.LIVEKIT_EGRESS_OUTPUT_DIR) / name
        if egress_file.is_file():
            return egress_file
    return recordings_root() / name


def recording_api_url(call_id: int) -> str:
    return f"{settings.API_V1_PREFIX}/calls/{call_id}/recording"


async def get_recording_for_call(db: AsyncSession, call_id: int) -> Recording | None:
    result = await db.execute(select(Recording).where(Recording.call_id == call_id))
    return result.scalar_one_or_none()


async def upsert_recording(
    db: AsyncSession,
    *,
    call_id: int,
    file_path: Path,
    duration_seconds: int | None = None,
) -> Recording | None:
    if not file_path.is_file():
        return None

    size = file_path.stat().st_size
    result = await db.execute(select(Recording).where(Recording.call_id == call_id))
    row = result.scalar_one_or_none()
    url = recording_api_url(call_id)
    if row:
        row.file_path = str(file_path)
        row.file_url = url
        row.size_bytes = size
        if duration_seconds is not None:
            row.duration_seconds = duration_seconds
    else:
        row = Recording(
            call_id=call_id,
            file_path=str(file_path),
            file_url=url,
            format="ogg",
            size_bytes=size,
            duration_seconds=duration_seconds,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
