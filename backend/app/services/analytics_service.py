from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_agent import AIAgent
from app.db.models.call_log import CallLog, CallStatus
from app.db.models.campaign import Campaign, CampaignStatus, Lead, LeadStatus
from app.db.models.transcript import Transcript


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class AnalyticsService:
    async def get_dashboard_stats_old(
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

    async def get_dashboard_stats(
        self,
        db: AsyncSession,
        client_id: int,
        days: int = 30
    ) -> dict[str, Any]:

        today = _today_start()

        yesterday_start = today - timedelta(days=1)
        yesterday_end = today

        def _client(q):
            return q.where(CallLog.client_id == client_id)
        
        def percent_change(current, previous):
            if previous == 0:
                return 0

            return round(
                ((current - previous) / previous) * 100,
                1
            )


        # ─────────────────────────
        # Today Calls
        # ─────────────────────────

        today_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today
                )
            )
        ) or 0

        yesterday_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= yesterday_start,
                    CallLog.started_at < yesterday_end
                )
            )
        ) or 0



        connected_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today,
                    CallLog.status.in_([
                        CallStatus.COMPLETED,
                        CallStatus.TRANSFERRED
                    ])
                )
            )
        ) or 0


        yesterday_connected_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= yesterday_start,
                    CallLog.started_at < yesterday_end,
                    CallLog.status.in_([
                        CallStatus.COMPLETED,
                        CallStatus.TRANSFERRED
                    ])
                )
            )
        ) or 0



        transferred_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today,
                    CallLog.status == CallStatus.TRANSFERRED
                )
            )
        ) or 0



        active_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.status.in_([
                        CallStatus.RINGING,
                        CallStatus.ACTIVE
                    ]),
                    CallLog.ended_at.is_(None)
                )
            )
        ) or 0



        # ─────────────────────────
        # Sentiment
        # ─────────────────────────

        positive_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today,
                    CallLog.sentiment_score >= 0.3
                )
            )
        ) or 0



        negative_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today,
                    CallLog.sentiment_score <= -0.3
                )
            )
        ) or 0



        neutral_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= today,
                    CallLog.sentiment_score > -0.3,
                    CallLog.sentiment_score < 0.3
                )
            )
        ) or 0


        # =========================================================
        # SENTIMENT YESTERDAY
        # =========================================================

        yesterday_positive_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= yesterday_start,
                    CallLog.started_at < yesterday_end,
                    CallLog.sentiment_score >= 0.3
                )
            )
        ) or 0



        yesterday_neutral_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= yesterday_start,
                    CallLog.started_at < yesterday_end,
                    CallLog.sentiment_score > -0.3,
                    CallLog.sentiment_score < 0.3
                )
            )
        ) or 0



        yesterday_negative_calls = await db.scalar(
            _client(
                select(func.count(CallLog.id))
                .where(
                    CallLog.started_at >= yesterday_start,
                    CallLog.started_at < yesterday_end,
                    CallLog.sentiment_score <= -0.3
                )
            )
        ) or 0



        # ─────────────────────────
        # Technical
        # ─────────────────────────

        today_avg_duration = await db.scalar(
            _client(
                select(func.avg(CallLog.duration_seconds))
                .where(
                    CallLog.started_at >= today,
                    CallLog.status.in_([
                        CallStatus.COMPLETED,
                        CallStatus.TRANSFERRED
                    ])
                )
            )
        ) or 0



        ai_cost_today = await db.scalar(
            _client(
                select(
                    func.coalesce(
                        func.sum(CallLog.total_cost),
                        0
                    )
                )
                .where(
                    CallLog.started_at >= today
                )
            )
        ) or 0



        # ─────────────────────────
        # Rates
        # ─────────────────────────

        connect_rate = (
            connected_calls / today_calls * 100
            if today_calls else 0
        )


        transfer_rate = (
            transferred_calls / connected_calls * 100
            if connected_calls else 0
        )


        positive_rate = (
            positive_calls / connected_calls * 100
            if connected_calls else 0
        )


        neutral_rate = (
            neutral_calls / connected_calls * 100
            if connected_calls else 0
        )


        negative_rate = (
            negative_calls / connected_calls * 100
            if connected_calls else 0
        )


        return {

            # KPI
            "today_calls": today_calls,

            "connected_calls": connected_calls,

            "answer_rate": round(
                connect_rate,
                1
            ),


            "positive_calls": positive_calls,

            "positive_rate": round(
                positive_rate,
                1
            ),


            "neutral_calls": neutral_calls,

            "neutral_rate": round(
                neutral_rate,
                1
            ),


            "negative_calls": negative_calls,

            "negative_rate": round(
                negative_rate,
                1
            ),

            # KPI CHANGES

            "today_calls_change": percent_change(
                today_calls,
                yesterday_calls
            ),


            "connected_calls_change": percent_change(
                connected_calls,
                yesterday_connected_calls
            ),


            "positive_calls_change": percent_change(
                positive_calls,
                yesterday_positive_calls
            ),


            "neutral_calls_change": percent_change(
                neutral_calls,
                yesterday_neutral_calls
            ),


            "negative_calls_change": percent_change(
                negative_calls,
                yesterday_negative_calls
            ),


            # extra cards
            "active_calls": active_calls,

            "transfer_rate": round(
                transfer_rate,
                1
            ),

            "today_avg_duration_seconds": round(
                float(today_avg_duration),
                1
            ),

            "ai_cost_today": round(
                float(ai_cost_today),
                4
            )
        }
    




    async def get_call_volume_trend(
        self,
        db: AsyncSession,
        client_id: int,
        days: int = 14
    ) -> list[dict[str, Any]]:

        start_date = (
            datetime.now(timezone.utc)
            - timedelta(days=days)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )


        result = await db.execute(
            select(
                func.date(CallLog.started_at).label("date"),
                func.count(CallLog.id).label("calls")
            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= start_date
            )
            .group_by(
                func.date(CallLog.started_at)
            )
            .order_by(
                func.date(CallLog.started_at)
            )
        )


        rows = result.all()


        # map existing DB data
        volume_map = {
            str(row.date): row.calls
            for row in rows
        }


        # fill missing days with 0
        response = []

        for i in range(days):

            date = start_date + timedelta(days=i)

            key = date.strftime("%Y-%m-%d")

            response.append(
                {
                    "day": date.strftime("%b %d").replace(" 0", " "),
                    "calls": volume_map.get(key, 0)
                }
            )



        return response
    

    async def get_call_outcome_distribution(
        self,
        db: AsyncSession,
        client_id: int,
    ) -> list[dict[str, Any]]:

        today = _today_start()


        positive_calls = await db.scalar(
            select(func.count(CallLog.id))
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= today,
                CallLog.sentiment_score >= 0.3
            )
        ) or 0



        neutral_calls = await db.scalar(
            select(func.count(CallLog.id))
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= today,
                CallLog.sentiment_score > -0.3,
                CallLog.sentiment_score < 0.3
            )
        ) or 0



        negative_calls = await db.scalar(
            select(func.count(CallLog.id))
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= today,
                CallLog.sentiment_score <= -0.3
            )
        ) or 0



        return [
            {
                "name": "Positive",
                "value": positive_calls,
                "color": "#6D28D9"
            },
            {
                "name": "Neutral",
                "value": neutral_calls,
                "color": "#8B5CF6"
            },
            {
                "name": "Negative",
                "value": negative_calls,
                "color": "#C4B5FD"
            }
        ]


    async def get_agent_performance_ranking(
        self,
        db: AsyncSession,
        client_id: int
    ) -> list[dict[str, Any]]:

        # Today start UTC
        now = datetime.now(timezone.utc)

        today_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )


        result = await db.execute(
            select(
                AIAgent.name.label("agent_name"),

                func.count(CallLog.id).label("total_calls"),

                func.sum(
                    case(
                        (
                            CallLog.sentiment_score >= 0.3,
                            1
                        ),
                        else_=0
                    )
                ).label("positive_calls")

            )
            .join(
                AIAgent,
                AIAgent.id == CallLog.agent_id
            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= today_start
            )
            .group_by(
                AIAgent.name
            )
            .order_by(
                func.count(CallLog.id).desc()
            )
            .limit(10)
        )


        rows = result.all()


        ranking = []


        for r in rows:

            calls = int(r.total_calls or 0)
            positive = int(r.positive_calls or 0)


            ranking.append({

                "name": r.agent_name,

                # value used by frontend bar chart
                "value": round(
                    positive / calls * 100,
                    1
                ) if calls else 0

            })


        return ranking
    




    async def get_call_duration_analysis(
        self,
        db: AsyncSession,
        client_id: int
    ) -> list[dict[str, Any]]:

        # Today UTC start
        now = datetime.now(timezone.utc)

        today_start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )


        result = await db.execute(
            select(
                extract(
                    "hour",
                    CallLog.started_at
                ).label("hour"),

                func.avg(
                    CallLog.duration_seconds
                ).label("avg_duration"),

                func.count(
                    CallLog.id
                ).label("calls")

            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= today_start,
                CallLog.duration_seconds.isnot(None)
            )
            .group_by(
                extract(
                    "hour",
                    CallLog.started_at
                )
            )
            .order_by(
                extract(
                    "hour",
                    CallLog.started_at
                )
            )
        )


        rows = result.all()


        output = []


        for r in rows:

            hour = int(r.hour)

            # Convert 24h to frontend format
            if hour == 0:
                label = "12am"
            elif hour < 12:
                label = f"{hour}am"
            elif hour == 12:
                label = "12pm"
            else:
                label = f"{hour-12}pm"


            output.append({

                "hour": label,

                "seconds": round(
                    float(r.avg_duration or 0),
                    1
                ),

                "calls": int(
                    r.calls or 0
                )

            })


        return output
    





    async def get_business_performance(
        self,
        db: AsyncSession,
        client_id: int,
    ):
        now = datetime.now(timezone.utc)

        current_year = now.year

        current_year_start = datetime(
            current_year,
            1,
            1,
            tzinfo=timezone.utc,
        )

        previous_year_start = datetime(
            current_year - 1,
            1,
            1,
            tzinfo=timezone.utc,
        )

        previous_year_end = current_year_start

        # ============================================
        # Monthly Outcomes (Current Year)
        # ============================================

        result = await db.execute(
            select(
                extract("year", CallLog.started_at).label("year"),
                extract("month", CallLog.started_at).label("month"),

                func.sum(
                    case(
                        (CallLog.sentiment_score >= 0.3, 1),
                        else_=0,
                    )
                ).label("positive"),

                func.sum(
                    case(
                        (
                            (CallLog.sentiment_score > -0.3)
                            &
                            (CallLog.sentiment_score < 0.3),
                            1,
                        ),
                        else_=0,
                    )
                ).label("neutral"),

                func.sum(
                    case(
                        (CallLog.sentiment_score <= -0.3, 1),
                        else_=0,
                    )
                ).label("negative"),
            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= current_year_start,
            )
            .group_by(
                extract("year", CallLog.started_at),
                extract("month", CallLog.started_at),
            )
            .order_by(
                extract("year", CallLog.started_at),
                extract("month", CallLog.started_at),
            )
        )

        rows = result.all()

        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]

        monthly = [
            {
                "year": int(r.year),
                "month": months[int(r.month) - 1],
                "Positive": int(r.positive or 0),
                "Neutral": int(r.neutral or 0),
                "Negative": int(r.negative or 0),
            }
            for r in rows
        ]

        # ============================================
        # Current Year KPIs
        # ============================================

        current = (
            await db.execute(
                select(
                    func.count(CallLog.id).label("calls"),

                    func.avg(CallLog.duration_seconds)
                    .label("avg_duration"),

                    func.sum(
                        case(
                            (CallLog.sentiment_score >= 0.3, 1),
                            else_=0,
                        )
                    ).label("positive_calls"),
                )
                .where(
                    CallLog.client_id == client_id,
                    CallLog.started_at >= current_year_start,
                )
            )
        ).one()

        # ============================================
        # Previous Year KPIs
        # ============================================

        previous = (
            await db.execute(
                select(
                    func.count(CallLog.id).label("calls"),

                    func.avg(CallLog.duration_seconds)
                    .label("avg_duration"),

                    func.sum(
                        case(
                            (CallLog.sentiment_score >= 0.3, 1),
                            else_=0,
                        )
                    ).label("positive_calls"),
                )
                .where(
                    CallLog.client_id == client_id,
                    CallLog.started_at >= previous_year_start,
                    CallLog.started_at < previous_year_end,
                )
            )
        ).one()

        current_calls = int(current.calls or 0)
        previous_calls = int(previous.calls or 0)

        current_positive_rate = (
            (int(current.positive_calls or 0) / current_calls * 100)
            if current_calls
            else 0
        )

        previous_positive_rate = (
            (int(previous.positive_calls or 0) / previous_calls * 100)
            if previous_calls
            else 0
        )

        current_duration = float(current.avg_duration or 0)
        previous_duration = float(previous.avg_duration or 0)

        total_calls_yoy = (
            ((current_calls - previous_calls) / previous_calls * 100)
            if previous_calls
            else 0
        )

        positive_rate_yoy = (
            current_positive_rate - previous_positive_rate
        )

        duration_change = (
            current_duration - previous_duration
        )

        return {
            "monthly_outcomes": monthly,

            "kpis": {
                "total_calls": current_calls,
                "total_calls_yoy": round(total_calls_yoy, 1),

                "positive_rate": round(current_positive_rate, 1),
                "positive_rate_yoy": round(positive_rate_yoy, 1),

                "avg_call_duration_seconds": round(current_duration, 1),
                "avg_call_duration_change_seconds": round(duration_change, 1),
            },
        }
    


    async def get_agent_positive_rate(
        self,
        db: AsyncSession,
        client_id: int,
        days: int = 7
    ) -> list[dict[str, Any]]:

        since = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(
                func.date(CallLog.started_at).label("day"),
                CallLog.agent_id,
                AIAgent.name.label("agent_name"),

                func.count(CallLog.id).label("total_calls"),

                func.sum(
                    case(
                        (
                            CallLog.sentiment_score >= 0.3,
                            1
                        ),
                        else_=0
                    )
                ).label("positive_calls")

            )
            .join(
                AIAgent,
                AIAgent.id == CallLog.agent_id,
                isouter=True
            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= since,
                CallLog.agent_id.isnot(None)
            )
            .group_by(
                func.date(CallLog.started_at),
                CallLog.agent_id,
                AIAgent.name
            )
            .order_by(
                func.date(CallLog.started_at)
            )
        )


        rows = result.all()


        # Transform for Recharts LineChart
        grouped = {}

        for r in rows:

            day = r.day.strftime("%b %d")

            if day not in grouped:
                grouped[day] = {
                    "day": day
                }


            total = int(r.total_calls or 0)
            positive = int(r.positive_calls or 0)


            grouped[day][r.agent_name or f"Agent #{r.agent_id}"] = round(
                (positive / total * 100),
                1
            ) if total else 0



        return list(grouped.values())
    


    async def get_technical_metrics(
        self,
        db: AsyncSession,
        client_id: int,
    ) -> dict[str, Any]:

        today = datetime.now(timezone.utc).date()

        start = datetime.combine(
            today,
            datetime.min.time(),
            tzinfo=timezone.utc
        )

        end = start + timedelta(days=1)


        # Calls today
        result = await db.execute(
            select(
                func.avg(CallLog.duration_seconds).label("avg_duration"),
                func.avg(Transcript.latency_ms).label("avg_latency"),

                func.count(
                    func.distinct(CallLog.id)
                ).label("total_calls"),

                func.count(
                    func.distinct(
                        case(
                            (CallLog.status == CallStatus.COMPLETED, CallLog.id),
                            else_=None,
                        )
                    )
                ).label("completed_calls"),
            )
            .join(
                Transcript,
                Transcript.call_id == CallLog.id,
                isouter=True,
            )
            .where(
                CallLog.client_id == client_id,
                CallLog.started_at >= start,
                CallLog.started_at < end,
            )
        )


        row = result.one()


        total_calls = int(row.total_calls or 0)

        completed = int(row.completed_calls or 0)

        # webhook_success = int(row.webhook_success or 0)


        return {
            "avg_call_duration_seconds": round(
                float(row.avg_duration or 0),
                1,
            ),

            "first_call_resolution": round(
                completed / total_calls * 100,
                1,
            ) if total_calls else 0,

            "latency_ms": round(
                float(row.avg_latency or 0),
                1,
            ),

            "api_uptime": 99.98,

            "transcription_accuracy": 0,

            "webhook_delivery_rate": 0,
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
