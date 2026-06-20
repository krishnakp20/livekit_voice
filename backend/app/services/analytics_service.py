from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_agent import AIAgent
from app.db.models.call_log import CallLog, CallStatus
from app.db.models.campaign import Campaign, CampaignStatus, Lead, LeadStatus
from app.db.models.transcript import Transcript


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class AnalyticsService:
    async def get_dashboard_stats(
        self, db: AsyncSession, client_id: int, days: int = 30
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        today = _today_start()

        def _client(q):
            return q.where(CallLog.client_id == client_id)

        # ── Period (default 30d) totals ─────────────────────────────────────
        total_calls = await db.scalar(_client(
            select(func.count(CallLog.id)).where(CallLog.started_at >= since)
        )) or 0
        completed = await db.scalar(_client(
            select(func.count(CallLog.id)).where(
                CallLog.status == CallStatus.COMPLETED, CallLog.started_at >= since
            )
        )) or 0
        avg_duration = await db.scalar(_client(
            select(func.avg(CallLog.duration_seconds)).where(
                CallLog.status == CallStatus.COMPLETED, CallLog.started_at >= since
            )
        )) or 0
        avg_sentiment = await db.scalar(_client(
            select(func.avg(CallLog.sentiment_score)).where(CallLog.started_at >= since)
        )) or 0
        avg_latency = await db.scalar(
            select(func.avg(Transcript.latency_ms))
            .join(CallLog, Transcript.call_id == CallLog.id)
            .where(CallLog.client_id == client_id, CallLog.started_at >= since)
        ) or 0

        # ── Real-time + today KPIs ──────────────────────────────────────────
        active_calls = await db.scalar(_client(
            select(func.count(CallLog.id)).where(
                CallLog.status.in_([CallStatus.RINGING, CallStatus.ACTIVE]),
                CallLog.ended_at.is_(None),
            )
        )) or 0

        today_calls = await db.scalar(_client(
            select(func.count(CallLog.id)).where(CallLog.started_at >= today)
        )) or 0
        today_answered = await db.scalar(_client(
            select(func.count(CallLog.id)).where(
                CallLog.started_at >= today,
                CallLog.status.in_([CallStatus.COMPLETED, CallStatus.TRANSFERRED]),
            )
        )) or 0
        today_transferred = await db.scalar(_client(
            select(func.count(CallLog.id)).where(
                CallLog.started_at >= today, CallLog.status == CallStatus.TRANSFERRED
            )
        )) or 0
        today_avg_duration = await db.scalar(_client(
            select(func.avg(CallLog.duration_seconds)).where(
                CallLog.started_at >= today,
                CallLog.status.in_([CallStatus.COMPLETED, CallStatus.TRANSFERRED]),
            )
        )) or 0
        ai_cost_today = await db.scalar(_client(
            select(func.coalesce(func.sum(CallLog.total_cost), 0)).where(
                CallLog.started_at >= today
            )
        )) or 0

        answer_rate = (today_answered / today_calls * 100) if today_calls else 0
        transfer_rate = (today_transferred / today_answered * 100) if today_answered else 0
        conversion_rate = (completed / total_calls * 100) if total_calls else 0

        return {
            # period
            "total_calls": total_calls,
            "completed_calls": completed,
            "conversion_rate": round(conversion_rate, 1),
            "avg_handling_time_seconds": round(float(avg_duration or 0), 1),
            "avg_sentiment": round(float(avg_sentiment or 0), 3),
            "avg_ai_latency_ms": round(float(avg_latency or 0), 1),
            "period_days": days,
            # real-time + today
            "active_calls": active_calls,
            "today_calls": today_calls,
            "answer_rate": round(answer_rate, 1),
            "transfer_rate": round(transfer_rate, 1),
            "today_avg_duration_seconds": round(float(today_avg_duration or 0), 1),
            "ai_cost_today": round(float(ai_cost_today or 0), 4),
        }

    async def get_campaign_performance(
        self, db: AsyncSession, client_id: int
    ) -> dict[str, Any]:
        total_campaigns = await db.scalar(
            select(func.count(Campaign.id)).where(Campaign.client_id == client_id)
        ) or 0
        running = await db.scalar(
            select(func.count(Campaign.id)).where(
                Campaign.client_id == client_id, Campaign.status == CampaignStatus.RUNNING
            )
        ) or 0
        calls_made = await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.client_id == client_id, CallLog.campaign_id.isnot(None)
            )
        ) or 0
        connected = await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.client_id == client_id,
                CallLog.campaign_id.isnot(None),
                CallLog.status.in_([CallStatus.COMPLETED, CallStatus.TRANSFERRED]),
            )
        ) or 0
        qualified = await db.scalar(
            select(func.count(Lead.id)).where(
                Lead.client_id == client_id, Lead.status == LeadStatus.CONNECTED
            )
        ) or 0
        conversion = (connected / calls_made * 100) if calls_made else 0

        return {
            "total_campaigns": total_campaigns,
            "running_campaigns": running,
            "calls_made": calls_made,
            "connected_calls": connected,
            "qualified_leads": qualified,
            "conversion_rate": round(conversion, 1),
        }

    async def get_agent_performance(
        self, db: AsyncSession, client_id: int, days: int = 30
    ) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await db.execute(
            select(
                CallLog.agent_id,
                AIAgent.name.label("agent_name"),
                func.count(CallLog.id).label("calls"),
                func.avg(CallLog.duration_seconds).label("avg_duration"),
                func.avg(CallLog.sentiment_score).label("avg_sentiment"),
                func.avg(CallLog.total_cost).label("avg_cost"),
                func.sum(
                    case((CallLog.status == CallStatus.COMPLETED, 1), else_=0)
                ).label("completed"),
                func.sum(
                    case((CallLog.status == CallStatus.TRANSFERRED, 1), else_=0)
                ).label("transferred"),
            )
            .join(AIAgent, AIAgent.id == CallLog.agent_id, isouter=True)
            .where(CallLog.client_id == client_id, CallLog.started_at >= since)
            .group_by(CallLog.agent_id, AIAgent.name)
            .order_by(func.count(CallLog.id).desc())
        )
        rows = result.all()
        out = []
        for r in rows:
            calls = int(r.calls or 0)
            completed = int(r.completed or 0)
            transferred = int(r.transferred or 0)
            out.append({
                "agent_id": r.agent_id,
                "agent_name": r.agent_name or f"Agent #{r.agent_id}",
                "calls_handled": calls,
                "avg_duration_seconds": round(float(r.avg_duration or 0), 1),
                "avg_sentiment": round(float(r.avg_sentiment or 0), 3),
                "cost_per_call": round(float(r.avg_cost or 0), 4),
                "success_rate": round(completed / calls * 100, 1) if calls else 0.0,
                "transfer_pct": round(transferred / calls * 100, 1) if calls else 0.0,
            })
        return out


analytics_service = AnalyticsService()
