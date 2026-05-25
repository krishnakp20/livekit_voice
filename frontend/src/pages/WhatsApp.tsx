import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getWhatsAppLogs } from "@/lib/api";

export default function WhatsApp() {
  const [logs, setLogs] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    getWhatsAppLogs().then((r) => setLogs(r.data));
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">WhatsApp Integration</h2>
      <p className="text-sm text-slate-500 mb-4">
        Auto-sends call summaries, missed call alerts, lead status updates, and daily reports.
      </p>
      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="text-left px-4 py-3">Recipient</th>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Time</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id as number} className="border-b border-slate-50">
                  <td className="px-4 py-3 font-mono">{l.recipient as string}</td>
                  <td className="px-4 py-3">{l.message_type as string}</td>
                  <td className="px-4 py-3"><Badge status={l.status as string} /></td>
                  <td className="px-4 py-3 text-slate-400">{l.created_at as string}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
