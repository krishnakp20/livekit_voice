import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AdminUser, CurrentUser, DbSession
from app.db.models.ai_agent import AIAgent
from app.schemas.agent import AIAgentCreate, AIAgentResponse, AIAgentUpdate, AgentTestRequest, AgentTestResponse
from app.services.ai_service import ai_service

router = APIRouter()


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@router.get("", response_model=list[AIAgentResponse])
async def list_agents(db: DbSession, current_user: CurrentUser):
    result = await db.execute(
        select(AIAgent).where(AIAgent.client_id == current_user.client_id).order_by(AIAgent.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AIAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AIAgentCreate, db: DbSession, current_user: AdminUser):
    agent = AIAgent(
        client_id=current_user.client_id,
        slug=_slugify(data.name),
        **data.model_dump(),
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
    for key, value in data.model_dump(exclude_unset=True).items():
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
