import { useEffect, useState } from "react";
import { io } from "socket.io-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getLiveCalls } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface LiveCall {
  call_id: number;
  room_name: string;
  agent_name: string;
  caller_number: string | null;
  duration_seconds: number;
  status: string;
  agent_speaking: boolean;
  user_speaking: boolean;
  latest_transcript: string | null;
  sentiment_score: number | null;
}

export default function LiveCalls() {
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const [transcripts, setTranscripts] = useState<Record<number, string[]>>({});
  const { user } = useAuth();

  useEffect(() => {
    const load = () =>
      getLiveCalls()
        .then((r) => setCalls(r.data))
        .catch(() => setCalls([]));
    load();
    const interval = setInterval(load, 5000);

    const socket = io("/", { path: "/ws/socket.io", auth: { client_id: user?.client_id } });
    socket.on("transcript", (data: { call_id: number; content: string }) => {
      setTranscripts((prev) => ({
        ...prev,
        [data.call_id]: [...(prev[data.call_id] || []), data.content],
      }));
    });
    socket.on("sentiment", (data: { call_id: number; score: number }) => {
      setCalls((prev) =>
        prev.map((c) =>
          c.call_id === data.call_id ? { ...c, sentiment_score: data.score } : c
        )
      );
    });
    socket.on("call_update", () => load());

    return () => { clearInterval(interval); socket.disconnect(); };
  }, [user?.client_id]);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Live Calls</h2>
      {calls.length === 0 ? (
        <Card><CardContent className="py-12 text-center text-slate-500">No active calls</CardContent></Card>
      ) : (
        <div className="grid gap-4">
          {calls.map((call) => (
            <Card key={call.call_id} className="border-green-200">
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">{call.agent_name}</CardTitle>
                <Badge status={call.status} />
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-4">
                  <div>
                    <span className="text-slate-500">Number</span>
                    <p className="font-mono">{call.caller_number || "—"}</p>
                  </div>
                  <div><span className="text-slate-500">Duration</span><p>{call.duration_seconds}s</p></div>
                  <div><span className="text-slate-500">Agent Speaking</span><p>{call.agent_speaking ? "Yes" : "No"}</p></div>
                  <div><span className="text-slate-500">Sentiment</span><p>{call.sentiment_score?.toFixed(2) ?? "—"}</p></div>
                </div>
                <div className="bg-slate-50 rounded-lg p-3 max-h-40 overflow-y-auto text-sm">
                  {(transcripts[call.call_id] || (call.latest_transcript ? [call.latest_transcript] : [])).map((t, i) => (
                    <p key={i} className="mb-1">{t}</p>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
