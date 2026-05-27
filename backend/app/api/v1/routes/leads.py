import csv
import io

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.campaign import Lead
from app.schemas.campaign import LeadCreate, LeadResponse

router = APIRouter()


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
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    count = 0
    skipped = 0

    # Load existing phones for this campaign to skip duplicates
    existing_query = select(Lead.phone).where(Lead.client_id == current_user.client_id)
    if campaign_id:
        existing_query = existing_query.where(Lead.campaign_id == campaign_id)
    existing_result = await db.execute(existing_query)
    existing_phones: set[str] = {row[0] for row in existing_result.all()}

    for row in reader:
        phone = row.get("phone") or row.get("Phone") or row.get("PHONE")
        if not phone:
            continue
        phone = phone.strip()
        if phone in existing_phones:
            skipped += 1
            continue
        lead = Lead(
            client_id=current_user.client_id,
            campaign_id=campaign_id,
            phone=phone,
            name=row.get("name") or row.get("Name"),
            email=row.get("email") or row.get("Email"),
        )
        db.add(lead)
        existing_phones.add(phone)  # prevent in-batch duplicates too
        count += 1
    await db.flush()
    return {"imported": count, "skipped_duplicates": skipped}
