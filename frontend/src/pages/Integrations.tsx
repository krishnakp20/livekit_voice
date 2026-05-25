import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { getIntegrations } from "@/lib/api";

export default function Integrations() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    getIntegrations().then((r) => setItems(r.data));
  }, []);

  const types = [
    { type: "vicidial", name: "VICIdial", desc: "Ingroup mapping, auto-dial, lead sync, disposition sync" },
    { type: "whatsapp", name: "WhatsApp", desc: "Call summaries and alerts via Meta Cloud API" },
    { type: "crm", name: "CRM", desc: "Sync leads and call outcomes to your CRM" },
    { type: "webhook", name: "Webhook", desc: "Custom event webhooks for external systems" },
  ];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Integrations</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {types.map((t) => {
          const connected = items.some((i) => i.integration_type === t.type);
          return (
            <Card key={t.type}>
              <CardContent className="py-4">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="font-semibold">{t.name}</h3>
                    <p className="text-sm text-slate-500 mt-1">{t.desc}</p>
                  </div>
                  <Badge status={connected ? "active" : "inactive"} />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
