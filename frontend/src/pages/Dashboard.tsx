import { useEffect, useState } from "react";
import { Bot, Phone, TrendingUp, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getDashboardStats, getLiveCalls } from "@/lib/api";

interface Stats {
  total_calls: number;
  completed_calls: number;
  conversion_rate: number;
  avg_handling_time_seconds: number;
  avg_sentiment: number;
  avg_ai_latency_ms: number;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [liveCount, setLiveCount] = useState(0);

  useEffect(() => {
    const refresh = () => {
      getDashboardStats().then((r) => setStats(r.data)).catch(() => {});
      getLiveCalls().then((r) => setLiveCount(r.data.length)).catch(() => setLiveCount(0));
    };
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, []);

  const cards = [
    { label: "Total Calls", value: stats?.total_calls ?? 0, icon: Phone, color: "text-blue-600" },
    { label: "Live Calls", value: liveCount, icon: Phone, color: "text-green-600" },
    { label: "Conversion Rate", value: `${stats?.conversion_rate ?? 0}%`, icon: TrendingUp, color: "text-purple-600" },
    { label: "Avg Handle Time", value: `${stats?.avg_handling_time_seconds ?? 0}s`, icon: Clock, color: "text-amber-600" },
    { label: "AI Latency", value: `${stats?.avg_ai_latency_ms ?? 0}ms`, icon: Bot, color: "text-brand-600" },
    { label: "Avg Sentiment", value: stats?.avg_sentiment?.toFixed(2) ?? "0", icon: TrendingUp, color: "text-emerald-600" },
  ];

  return (
    <div>
      <h2 className="text-2xl font-bold text-slate-900 mb-6">Dashboard</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {cards.map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardContent className="flex items-center gap-4 py-5">
              <div className={`p-3 rounded-xl bg-slate-50 ${color}`}>
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm text-slate-500">{label}</p>
                <p className="text-2xl font-bold">{value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Quick Start</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-600 space-y-2">
          <p>1. Create an AI Agent with your prompt and voice settings</p>
          <p>2. Configure SIP Trunks for inbound/outbound calls</p>
          <p>3. Set up Dispatch Rules to route DIDs to agents</p>
          <p>4. Launch campaigns or monitor live calls in real-time</p>
        </CardContent>
      </Card>
    </div>
  );
}
