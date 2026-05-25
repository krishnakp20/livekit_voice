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
    for row in reader:
        phone = row.get("phone") or row.get("Phone") or row.get("PHONE")
        if not phone:
            continue
        lead = Lead(
            client_id=current_user.client_id,
            campaign_id=campaign_id,
            phone=phone.strip(),
            name=row.get("name") or row.get("Name"),
            email=row.get("email") or row.get("Email"),
        )
        db.add(lead)
        count += 1
    await db.flush()
    return {"imported": count}
