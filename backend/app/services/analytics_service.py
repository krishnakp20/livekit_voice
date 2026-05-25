from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.call_log import CallLog, CallStatus
from app.db.models.transcript import Transcript


class AnalyticsService:
    async def get_dashboard_stats(
        self, db: AsyncSession, client_id: int, days: int = 30
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        total_calls = await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.client_id == client_id, CallLog.started_at >= since
            )
        ) or 0

        completed = await db.scalar(
            select(func.count(CallLog.id)).where(
                CallLog.client_id == client_id,
                CallLog.status == CallStatus.COMPLETED,
                CallLog.started_at >= since,
            )
        ) or 0

        avg_duration = await db.scalar(
            select(func.avg(CallLog.duration_seconds)).where(
                CallLog.client_id == client_id,
                CallLog.status == CallStatus.COMPLETED,
                CallLog.started_at >= since,
            )
        ) or 0

        avg_sentiment = await db.scalar(
            select(func.avg(CallLog.sentiment_score)).where(
                CallLog.client_id == client_id, CallLog.started_at >= since
            )
        ) or 0

        avg_latency = await db.scalar(
            select(func.avg(Transcript.latency_ms))
            .join(CallLog, Transcript.call_id == CallLog.id)
            .where(CallLog.client_id == client_id, CallLog.started_at >= since)
        ) or 0

        conversion_rate = (completed / total_calls * 100) if total_calls > 0 else 0

        return {
            "total_calls": total_calls,
            "completed_calls": completed,
            "conversion_rate": round(conversion_rate, 2),
            "avg_handling_time_seconds": round(float(avg_duration or 0), 1),
            "avg_sentiment": round(float(avg_sentiment or 0), 3),
            "avg_ai_latency_ms": round(float(avg_latency or 0), 1),
            "period_days": days,
        }

    async def get_agent_performance(
        self, db: AsyncSession, client_id: int, days: int = 30
    ) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        result = await db.execute(
            select(
                CallLog.agent_id,
                func.count(CallLog.id).label("call_count"),
                func.avg(CallLog.duration_seconds).label("avg_duration"),
                func.avg(CallLog.sentiment_score).label("avg_sentiment"),
            )
            .where(CallLog.client_id == client_id, CallLog.started_at >= since)
            .group_by(CallLog.agent_id)
        )
        rows = result.all()
        return [
            {
                "agent_id": r.agent_id,
                "call_count": r.call_count,
                "avg_duration_seconds": round(float(r.avg_duration or 0), 1),
                "avg_sentiment": round(float(r.avg_sentiment or 0), 3),
            }
            for r in rows
        ]


analytics_service = AnalyticsService()
