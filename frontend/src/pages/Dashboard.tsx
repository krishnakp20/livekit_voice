import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getDashboardStats,
  getLiveCalls,
  getCampaignPerformance,
  getAgentPerformance,
  getSystemHealth,
} from "@/lib/api";

// ─────────────────────────── helpers ───────────────────────────
function fmtDuration(sec: number | null | undefined): string {
  const s = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function sentiment(score: number | null | undefined) {
  if (score == null) return { label: "—", cls: "text-slate-400" };
  if (score >= 0.3) return { label: "Positive", cls: "text-emerald-600" };
  if (score <= -0.3) return { label: "Negative", cls: "text-red-600" };
  return { label: "Neutral", cls: "text-slate-500" };
}

const HEALTH_COLORS: Record<string, string> = {
  operational: "bg-emerald-500",
  configured: "bg-emerald-500",
  unknown: "bg-slate-300",
  "not configured": "bg-amber-400",
  down: "bg-red-500",
};

// ─────────────────────────── small components ───────────────────────────
function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

function HealthCard({ label, state }: { label: string; state: string }) {
  const dot = HEALTH_COLORS[state] || "bg-slate-300";
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div>
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="text-xs capitalize text-slate-400">{state}</p>
      </div>
      <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{children}</h3>
      {right}
    </div>
  );
}

// ─────────────────────────── types ───────────────────────────
interface Stats {
  active_calls: number;
  today_calls: number;
  answer_rate: number;
  transfer_rate: number;
  today_avg_duration_seconds: number;
  ai_cost_today: number;
}
interface LiveCall {
  call_id: number;
  caller_number: string | null;
  agent_name: string;
  duration_seconds: number;
  status: string;
  sentiment_score: number | null;
}
interface Campaign {
  total_campaigns: number;
  running_campaigns: number;
  calls_made: number;
  connected_calls: number;
  qualified_leads: number;
  conversion_rate: number;
}
interface AgentPerf {
  agent_id: number;
  agent_name: string;
  calls_handled: number;
  avg_duration_seconds: number;
  transfer_pct: number;
  success_rate: number;
  cost_per_call: number;
}
interface Health {
  livekit: string;
  asterisk: string;
  sip_trunk: string;
  stt: string;
  tts: string;
  llm: string;
}

// ─────────────────────────── page ───────────────────────────
export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [live, setLive] = useState<LiveCall[]>([]);
  const [camp, setCamp] = useState<Campaign | null>(null);
  const [agents, setAgents] = useState<AgentPerf[]>([]);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    const fast = () => {
      getDashboardStats().then((r) => setStats(r.data)).catch(() => {});
      getLiveCalls().then((r) => setLive(r.data)).catch(() => setLive([]));
    };
    const slow = () => {
      getCampaignPerformance().then((r) => setCamp(r.data)).catch(() => {});
      getAgentPerformance().then((r) => setAgents(r.data)).catch(() => setAgents([]));
      getSystemHealth().then((r) => setHealth(r.data)).catch(() => setHealth(null));
    };
    fast();
    slow();
    const t1 = setInterval(fast, 5000); // real-time row every 5s
    const t2 = setInterval(slow, 30000);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, []);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-900">Operations Overview</h2>
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" /> Live
        </span>
      </div>

      {/* KPI ROW */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Active Calls" value={String(stats?.active_calls ?? 0)} sub="real-time" />
        <Kpi label="Today's Calls" value={String(stats?.today_calls ?? 0)} />
        <Kpi label="Answer Rate" value={`${stats?.answer_rate ?? 0}%`} sub="today" />
        <Kpi label="Transfer Rate" value={`${stats?.transfer_rate ?? 0}%`} sub="today" />
        <Kpi label="Avg Duration" value={fmtDuration(stats?.today_avg_duration_seconds)} sub="today" />
        <Kpi label="AI Cost Today" value={`$${(stats?.ai_cost_today ?? 0).toFixed(2)}`} />
      </div>

      {/* SYSTEM HEALTH */}
      <div>
        <SectionTitle>System Health</SectionTitle>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <HealthCard label="LiveKit" state={health?.livekit ?? "unknown"} />
          <HealthCard label="Asterisk / SIP" state={health?.asterisk ?? "unknown"} />
          <HealthCard label="SIP Trunk" state={health?.sip_trunk ?? "unknown"} />
          <HealthCard label="STT (Deepgram)" state={health?.stt ?? "unknown"} />
          <HealthCard label="TTS (Cartesia)" state={health?.tts ?? "unknown"} />
          <HealthCard label="LLM" state={health?.llm ?? "unknown"} />
        </div>
      </div>

      {/* REAL-TIME CALL ACTIVITY */}
      <div>
        <SectionTitle right={<Link to="/live-calls" className="text-xs text-brand-600 hover:underline">View all</Link>}>
          Real-Time Call Activity
        </SectionTitle>
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5 font-medium">Customer</th>
                <th className="px-4 py-2.5 font-medium">Agent / Bot</th>
                <th className="px-4 py-2.5 font-medium">Duration</th>
                <th className="px-4 py-2.5 font-medium">State</th>
                <th className="px-4 py-2.5 font-medium">Sentiment</th>
                <th className="px-4 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {live.map((c) => {
                const s = sentiment(c.sentiment_score);
                const active = c.status === "active";
                return (
                  <tr key={c.call_id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2.5 font-mono text-slate-700">{c.caller_number || "—"}</td>
                    <td className="px-4 py-2.5 text-slate-600">{c.agent_name}</td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-600">{fmtDuration(c.duration_seconds)}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`h-2 w-2 rounded-full ${active ? "bg-emerald-500" : "bg-amber-400"}`} />
                        <span className="capitalize text-slate-600">{c.status}</span>
                      </span>
                    </td>
                    <td className={`px-4 py-2.5 ${s.cls}`}>{s.label}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Link to="/live-calls" className="text-xs text-brand-600 hover:underline">Monitor</Link>
                    </td>
                  </tr>
                );
              })}
              {live.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                    No active calls right now
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* CAMPAIGN PERFORMANCE */}
      <div>
        <SectionTitle right={<Link to="/campaigns" className="text-xs text-brand-600 hover:underline">Manage</Link>}>
          Campaign Performance
        </SectionTitle>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Total Campaigns" value={camp?.total_campaigns ?? 0} />
          <StatCard label="Running" value={camp?.running_campaigns ?? 0} />
          <StatCard label="Calls Made" value={camp?.calls_made ?? 0} />
          <StatCard label="Connected" value={camp?.connected_calls ?? 0} />
          <StatCard label="Qualified Leads" value={camp?.qualified_leads ?? 0} />
          <StatCard label="Conversion" value={`${camp?.conversion_rate ?? 0}%`} />
        </div>
      </div>

      {/* AI AGENT PERFORMANCE */}
      <div>
        <SectionTitle right={<Link to="/agents" className="text-xs text-brand-600 hover:underline">Manage agents</Link>}>
          AI Agent Performance
        </SectionTitle>
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2.5 font-medium">Agent</th>
                <th className="px-4 py-2.5 font-medium text-right">Calls</th>
                <th className="px-4 py-2.5 font-medium text-right">Avg Duration</th>
                <th className="px-4 py-2.5 font-medium text-right">Transfer %</th>
                <th className="px-4 py-2.5 font-medium text-right">Success %</th>
                <th className="px-4 py-2.5 font-medium text-right">Cost / Call</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.agent_id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2.5 font-medium text-slate-700">{a.agent_name}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{a.calls_handled}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{fmtDuration(a.avg_duration_seconds)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{a.transfer_pct}%</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-emerald-600">{a.success_rate}%</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">${a.cost_per_call.toFixed(3)}</td>
                </tr>
              ))}
              {agents.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                    No agent activity in the last 30 days
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
