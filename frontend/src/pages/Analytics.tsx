import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { getAgentPerformance, getDashboardStats } from "@/lib/api";

export default function Analytics() {
  const [stats, setStats] = useState<Record<string, number>>({});
  const [agents, setAgents] = useState<{ agent_id: number; call_count: number; avg_duration_seconds: number }[]>([]);

  useEffect(() => {
    getDashboardStats().then((r) => setStats(r.data));
    getAgentPerformance().then((r) => setAgents(r.data));
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Analytics</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: "Total Calls", key: "total_calls" },
          { label: "Completed", key: "completed_calls" },
          { label: "Conversion %", key: "conversion_rate" },
          { label: "Avg Sentiment", key: "avg_sentiment", format: (v: number) => v?.toFixed(2) ?? "0" },
          { label: "Avg Latency (ms)", key: "avg_ai_latency_ms" },
        ].map((item) => (
          <Card key={item.key}>
            <CardContent className="py-4 text-center">
              <p className="text-sm text-slate-500">{item.label}</p>
              <p className="text-2xl font-bold">
                {"format" in item && item.format
                  ? item.format(stats[item.key] as number)
                  : (stats[item.key] ?? 0)}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader><CardTitle>Agent Performance</CardTitle></CardHeader>
        <CardContent className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={agents}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="agent_id" tickFormatter={(v) => `Agent ${v}`} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="call_count" fill="#6366f1" name="Calls" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
