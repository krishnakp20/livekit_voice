import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { fetchCallRecordingBlob, getCall, getCalls } from "@/lib/api";

interface TranscriptEntry {
  id: number;
  speaker: string;
  content: string;
  sentiment: number | null;
  sequence: number;
}

interface CallRow {
  id: number;
  direction: string;
  caller_number: string | null;
  callee_number: string | null;
  duration_seconds: number | null;
  status: string;
  sentiment_score: number | null;
  started_at: string;
  has_recording: boolean;
  recording_url: string | null;
  transcripts?: TranscriptEntry[];
}

function displayNumber(c: CallRow): string {
  if (c.direction === "outbound") return c.callee_number || c.caller_number || "—";
  return c.caller_number || c.callee_number || "—";
}

function formatDateTime(iso: string): string {
  if (!iso) return "—";
  // Backend stores UTC. If the string has no timezone marker (no trailing Z
  // and no +hh:mm / -hh:mm offset), it's a naive UTC timestamp — append "Z"
  // so the browser parses it as UTC instead of local time.
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso.trim());
  const d = new Date(hasTz ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function sentimentLabel(score: number | null) {
  if (score == null) return "—";
  if (score >= 0.3) return `Positive (${score.toFixed(2)})`;
  if (score <= -0.3) return `Negative (${score.toFixed(2)})`;
  return `Neutral (${score.toFixed(2)})`;
}

function sentimentColor(score: number | null) {
  if (score == null) return "text-slate-500";
  if (score >= 0.3) return "text-green-600";
  if (score <= -0.3) return "text-red-600";
  return "text-amber-600";
}

export default function Calls() {
  const [calls, setCalls] = useState<CallRow[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CallRow | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState(false);
  const [loadingRecording, setLoadingRecording] = useState(false);

  useEffect(() => {
    getCalls()
      .then((r) => setCalls(r.data))
      .catch(() => setCalls([]));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    getCall(selectedId)
      .then((r) => setDetail(r.data))
      .catch(() => setDetail(null))
      .finally(() => setLoadingDetail(false));
  }, [selectedId]);

  useEffect(() => {
    if (!detail?.has_recording || !detail.id) {
      setRecordingUrl(null);
      setRecordingError(false);
      setLoadingRecording(false);
      return;
    }

    let objectUrl: string | null = null;
    let cancelled = false;
    setLoadingRecording(true);
    setRecordingError(false);

    fetchCallRecordingBlob(detail.id)
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setRecordingUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setRecordingUrl(null);
          setRecordingError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingRecording(false);
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setRecordingUrl(null);
    };
  }, [detail?.id, detail?.has_recording]);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Call History</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3">ID</th>
                  <th className="text-left px-4 py-3">Date & Time</th>
                  <th className="text-left px-4 py-3">Number</th>
                  <th className="text-left px-4 py-3">Direction</th>
                  <th className="text-left px-4 py-3">Duration</th>
                  <th className="text-left px-4 py-3">Status</th>
                  <th className="text-left px-4 py-3">Sentiment</th>
                  <th className="text-left px-4 py-3">Recording</th>
                </tr>
              </thead>
              <tbody>
                {calls.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                      No calls yet
                    </td>
                  </tr>
                )}
                {calls.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={`border-b border-slate-50 cursor-pointer hover:bg-slate-50 ${
                      selectedId === c.id ? "bg-brand-50" : ""
                    }`}
                  >
                    <td className="px-4 py-3">#{c.id}</td>
                    <td className="px-4 py-3 text-slate-600 text-xs">{formatDateTime(c.started_at)}</td>
                    <td className="px-4 py-3 font-mono">{displayNumber(c)}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        c.direction === "outbound"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-green-100 text-green-700"
                      }`}>
                        {c.direction === "outbound" ? "↑ Out" : "↓ In"}
                      </span>
                    </td>
                    <td className="px-4 py-3">{c.duration_seconds ? `${c.duration_seconds}s` : "—"}</td>
                    <td className="px-4 py-3">
                      <Badge status={c.status} />
                    </td>
                    <td className={`px-4 py-3 ${sentimentColor(c.sentiment_score)}`}>
                      {sentimentLabel(c.sentiment_score)}
                    </td>
                    <td className="px-4 py-3">{c.has_recording ? "Yes" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{selectedId ? `Call #${selectedId}` : "Call details"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {!selectedId && (
              <p className="text-slate-500">Select a call to view transcript, sentiment, and recording.</p>
            )}
            {selectedId && loadingDetail && <p className="text-slate-500">Loading…</p>}
            {detail && !loadingDetail && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-500">{detail.direction === "outbound" ? "Called" : "Caller"}</span>
                    <p className="font-mono">{displayNumber(detail)}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Date & Time</span>
                    <p className="text-xs">{formatDateTime(detail.started_at)}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-500">Direction</span>
                    <p>
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        detail.direction === "outbound"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-green-100 text-green-700"
                      }`}>
                        {detail.direction === "outbound" ? "↑ Outbound" : "↓ Inbound"}
                      </span>
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Sentiment</span>
                    <p className={sentimentColor(detail.sentiment_score)}>
                      {sentimentLabel(detail.sentiment_score)}
                    </p>
                  </div>
                </div>

                <div>
                  <span className="text-slate-500 block mb-2">Recording</span>
                  {loadingRecording && (
                    <p className="text-slate-500">Loading recording…</p>
                  )}
                  {recordingUrl && !loadingRecording && (
                    <audio controls className="w-full" src={recordingUrl}>
                      Your browser does not support audio playback.
                    </audio>
                  )}
                  {recordingError && !loadingRecording && (
                    <p className="text-red-600">Could not load recording. Try logging in again.</p>
                  )}
                  {!detail.has_recording && !loadingRecording && (
                    <p className="text-slate-500">
                      No recording file yet. Ensure Record Calls is enabled on the agent and the
                      worker saved the file after hangup — then select this call again.
                    </p>
                  )}
                </div>

                <div>
                  <span className="text-slate-500 block mb-2">Transcript</span>
                  <div className="max-h-64 overflow-y-auto space-y-2 bg-slate-50 rounded-lg p-3">
                    {(detail.transcripts || []).length === 0 && (
                      <p className="text-slate-500">No transcript entries</p>
                    )}
                    {(detail.transcripts || []).map((t) => (
                      <div key={t.id} className="text-xs">
                        <span className="font-semibold capitalize text-brand-700">{t.speaker}: </span>
                        <span>{t.content}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
