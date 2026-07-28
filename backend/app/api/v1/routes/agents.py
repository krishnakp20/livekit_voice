import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.crypto import encrypt_secret
from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.ai_agent import AIAgent
from app.schemas.agent import AIAgentCreate, AIAgentResponse, AIAgentUpdate, AgentTestRequest, AgentTestResponse
from app.services.ai_service import ai_service

router = APIRouter()

_KEY_FIELDS = ("stt_api_key", "llm_api_key", "tts_api_key")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _encrypt_key_fields(payload: dict) -> None:
    """Replace plaintext provider API keys in `payload` with their encrypted
    form (in place) before they're written to the DB. A blank string clears
    the stored key (falls back to the company's global key for that
    provider); a missing key means "leave unchanged" and is handled by the
    caller via exclude_unset, not here."""
    for field in _KEY_FIELDS:
        if field in payload:
            payload[field] = encrypt_secret(payload[field])


@router.get("", response_model=list[AIAgentResponse])
async def list_agents(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(AIAgent).where(AIAgent.client_id == current_user.client_id).order_by(AIAgent.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AIAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AIAgentCreate, db: DbSession, current_user: AdminUser):
    payload = data.model_dump()
    requested_client_id = payload.pop("client_id", None)
    _encrypt_key_fields(payload)

    # Use the explicit body client_id if given, else the user's (effective)
    # client_id — which for a super admin is set by the X-Client-Id header.
    client_id = requested_client_id or current_user.client_id
    if client_id is None:
        raise HTTPException(
            status_code=400,
            detail="No client selected. Pick a client first (super admin) or provide client_id.",
        )

    agent = AIAgent(
        client_id=client_id,
        slug=_slugify(data.name),
        **payload,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AIAgentResponse)
async def get_agent(agent_id: int, db: DbSession, current_user: CurrentUser):
    agent = await _get_agent(db, agent_id, current_user.client_id)
    return agent


@router.patch("/{agent_id}", response_model=AIAgentResponse)
async def update_agent(agent_id: int, data: AIAgentUpdate, db: DbSession, current_user: AdminUser):
    agent = await _get_agent(db, agent_id, current_user.client_id)
    update_payload = data.model_dump(exclude_unset=True)
    _encrypt_key_fields(update_payload)
    for key, value in update_payload.items():
        setattr(agent, key, value)
    if data.name:
        agent.slug = _slugify(data.name)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, db: DbSession, current_user: AdminUser):
    agent = await _get_agent(db, agent_id, current_user.client_id)
    await db.delete(agent)


@router.post("/{agent_id}/test", response_model=AgentTestResponse)
async def test_agent(agent_id: int, data: AgentTestRequest, db: DbSession, current_user: CurrentUser):
    agent = await _get_agent(db, agent_id, current_user.client_id)
    response, latency_ms = await ai_service.generate_response(agent, data.message)
    return AgentTestResponse(response=response, latency_ms=latency_ms)


async def _get_agent(db, agent_id: int, client_id: int) -> AIAgent:
    result = await db.execute(
        select(AIAgent).where(AIAgent.id == agent_id, AIAgent.client_id == client_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
