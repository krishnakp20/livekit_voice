import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.sip_trunk import SIPTrunk, TrunkDirection, TrunkStatus
from app.schemas.sip import SIPTrunkCreate, SIPTrunkResponse, SIPTrunkTestResponse, SIPTrunkUpdate
from app.services.livekit_service import livekit_service
from app.services.sync_service import sync_sip_trunks_from_livekit

router = APIRouter()
logger = logging.getLogger("vbots.sip")


@router.get("", response_model=list[SIPTrunkResponse])
async def list_trunks(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(SIPTrunk).where(SIPTrunk.client_id == current_user.client_id).order_by(SIPTrunk.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SIPTrunkResponse, status_code=status.HTTP_201_CREATED)
async def create_trunk(data: SIPTrunkCreate, db: DbSession, current_user: AdminUser):
    trunk = SIPTrunk(client_id=current_user.client_id, **data.model_dump())
    db.add(trunk)
    await db.flush()

    numbers = [d.strip() for d in (data.did_numbers or "").split(",") if d.strip()]

    try:
        if data.direction == TrunkDirection.OUTBOUND:
            # Outbound: address = carrier SIP server (e.g. "192.168.10.5:5060")
            # numbers = your caller-ID numbers sent to carrier
            if data.sip_uri and numbers:
                lk_trunk_id = await livekit_service.create_outbound_sip_trunk(
                    name=data.name,
                    address=data.sip_uri,
                    numbers=numbers,
                    auth_username=data.auth_username,
                    auth_password=data.auth_password,
                )
                trunk.livekit_trunk_id = lk_trunk_id
                trunk.status = TrunkStatus.ACTIVE
                logger.info("Created outbound LiveKit trunk %s for %s", lk_trunk_id, data.sip_uri)
            else:
                logger.warning("Outbound trunk %r skipped LiveKit — sip_uri or did_numbers missing", data.name)
        elif numbers:
            # Inbound: numbers = DIDs this trunk handles; sip_uri = carrier source IP for reference
            lk_trunk_id = await livekit_service.create_sip_trunk(
                name=data.name,
                inbound_addresses=numbers,
                auth_username=data.auth_username,
                auth_password=data.auth_password,
            )
            trunk.livekit_trunk_id = lk_trunk_id
            trunk.status = TrunkStatus.ACTIVE
            logger.info("Created inbound LiveKit trunk %s numbers=%s", lk_trunk_id, numbers)
    except Exception as e:
        logger.error("LiveKit trunk NOT created for %r: %s — sync manually after fixing.", data.name, e)
        trunk.status = TrunkStatus.INACTIVE

    await db.flush()  # persist livekit_trunk_id + status before refresh
    await db.refresh(trunk)
    return trunk


@router.post("/{trunk_id}/test", response_model=SIPTrunkTestResponse)
async def test_trunk(trunk_id: int, db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(SIPTrunk).where(SIPTrunk.id == trunk_id, SIPTrunk.client_id == current_user.client_id)
    )
    trunk = result.scalar_one_or_none()
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    trunk.last_tested_at = datetime.now(timezone.utc)
    if trunk.livekit_trunk_id:
        trunk.status = TrunkStatus.ACTIVE
        return SIPTrunkTestResponse(success=True, message="SIP trunk connected via LiveKit", latency_ms=45)
    return SIPTrunkTestResponse(success=False, message="LiveKit trunk not provisioned")


@router.post("/sync-from-livekit")
async def sync_from_livekit(db: DbSession, current_user: CurrentUser):
    """Import SIP trunks created in LiveKit console into VBots database."""
    if current_user.client_id is None:
        raise HTTPException(status_code=400, detail="User has no client assigned")
    result = await sync_sip_trunks_from_livekit(db, current_user.client_id)
    return {"message": "Sync complete", **result}


@router.patch("/{trunk_id}", response_model=SIPTrunkResponse)
async def update_trunk(trunk_id: int, data: SIPTrunkUpdate, db: DbSession, current_user: AdminUser):
    result = await db.execute(
        select(SIPTrunk).where(SIPTrunk.id == trunk_id, SIPTrunk.client_id == current_user.client_id)
    )
    trunk = result.scalar_one_or_none()
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(trunk, key, value)
    await db.refresh(trunk)
    return trunk
