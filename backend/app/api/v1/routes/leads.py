import csv
import io
import json
import re

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.campaign import Lead
from app.schemas.campaign import LeadCreate, LeadResponse

router = APIRouter()


# Columns that have dedicated DB fields — everything else is stored as a per-lead
# custom field in metadata_json for prompt personalisation ({customer_name}, etc.).
_RESERVED_COLUMNS = {"phone", "name", "email"}


def _norm_key(header: str) -> str:
    """Normalise a CSV header to a token key: lowercase, spaces/dashes → underscore."""
    k = (header or "").strip().lstrip("﻿").lower()
    return re.sub(r"[\s\-]+", "_", k)


def _extract_metadata(row: dict) -> dict[str, str]:
    """Collect every non-reserved column into a {normalised_key: value} dict.

    These become the {tokens} the worker substitutes into the prompt at call time,
    so any client can define their own fields just by adding CSV columns."""
    out: dict[str, str] = {}
    for header, value in row.items():
        if not header:
            continue
        key = _norm_key(header)
        if key in _RESERVED_COLUMNS or not key:
            continue
        val = (value or "").strip()
        if val:
            out[key] = val
    return out


def _clean_phone(raw: str) -> str | None:
    """Strip formatting chars; return None if result is too short or too long."""
    # Remove spaces, dashes, parentheses, dots — keep digits and leading +
    phone = re.sub(r"[\s\-\(\)\.]", "", raw.strip())
    if len(phone) < 5 or len(phone) > 20:
        return None
    return phone


def _decode_csv(content: bytes) -> str:
    """Try common encodings; handle UTF-8 BOM from Excel."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=400,
        detail="File encoding not supported. Open in Excel → Save As → CSV UTF-8 (comma delimited).",
    )


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    db: DbSession,
    current_user: CurrentUser,
    campaign_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
):
    query = select(Lead).where(Lead.client_id == current_user.client_id)
    if campaign_id:
        query = query.where(Lead.campaign_id == campaign_id)
    result = await db.execute(query.offset(skip).limit(limit).order_by(Lead.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(data: LeadCreate, db: DbSession, current_user: AdminUser):
    lead = Lead(client_id=current_user.client_id, **data.model_dump())
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_leads(
    db: DbSession,
    current_user: AdminUser,
    file: UploadFile = File(...),
    campaign_id: int | None = None,
):
    # ── File validation ──────────────────────────────────────────────────────
    fname = (file.filename or "").lower()
    if not fname.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Encoding: handle UTF-8 BOM (Excel) and Windows encodings ────────────
    text = _decode_csv(content)

    try:
        reader = csv.DictReader(io.StringIO(text))
        # Peek at headers to catch malformed CSV early
        headers = reader.fieldnames or []
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    # Normalise header names (strip BOM/whitespace just in case)
    norm_headers = [h.strip().lstrip("﻿").lower() for h in headers]
    if "phone" not in norm_headers:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV must have a 'phone' column. "
                f"Found columns: {', '.join(headers) or '(none)'}. "
                "Check that your file uses comma separators."
            ),
        )

    # ── Load existing phones to skip duplicates ──────────────────────────────
    existing_query = select(Lead.phone).where(Lead.client_id == current_user.client_id)
    if campaign_id:
        existing_query = existing_query.where(Lead.campaign_id == campaign_id)
    existing_result = await db.execute(existing_query)
    existing_phones: set[str] = {row[0] for row in existing_result.all()}

    count = 0
    skipped = 0
    invalid = 0

    for row in reader:
        # Case-insensitive column lookup
        raw_phone = (
            row.get("phone") or row.get("Phone") or row.get("PHONE") or ""
        )
        if not raw_phone:
            invalid += 1
            continue

        phone = _clean_phone(raw_phone)
        if phone is None:
            invalid += 1
            continue

        if phone in existing_phones:
            skipped += 1
            continue

        meta = _extract_metadata(row)
        lead = Lead(
            client_id=current_user.client_id,
            campaign_id=campaign_id,
            phone=phone,
            name=(row.get("name") or row.get("Name") or "").strip() or None,
            email=(row.get("email") or row.get("Email") or "").strip() or None,
            metadata_json=json.dumps(meta, ensure_ascii=False) if meta else None,
        )
        db.add(lead)
        existing_phones.add(phone)  # prevent in-batch duplicates too
        count += 1

    await db.flush()
    return {
        "imported": count,
        "skipped_duplicates": skipped,
        "skipped_invalid": invalid,
    }
