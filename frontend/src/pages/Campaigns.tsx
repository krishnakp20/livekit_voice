import { useEffect, useState } from "react";
import { Plus, Play, Pause, Phone } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import {
  createCampaign,
  dialCampaign,
  getAgents,
  getCampaigns,
  getCampaignStats,
  updateCampaignStatus,
} from "@/lib/api";

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState<Record<string, unknown>[]>([]);
  const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
  const [stats, setStats] = useState<Record<number, { total: number; leads: Record<string, number> }>>({});
  const [form, setForm] = useState({ name: "", agent_id: 0, max_retries: 3, dial_rate: 1 });
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    getCampaigns().then((r) => setCampaigns(r.data));
  };

  useEffect(() => {
    load();
    getAgents().then((r) => setAgents(r.data));
  }, []);

  useEffect(() => {
    campaigns.forEach((c) => {
      const id = c.id as number;
      getCampaignStats(id).then((r) => setStats((s) => ({ ...s, [id]: r.data })));
    });
  }, [campaigns]);

  const refreshStats = (id: number) => {
    getCampaignStats(id).then((r) => setStats((s) => ({ ...s, [id]: r.data })));
  };

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    await createCampaign({ ...form, agent_id: form.agent_id || agents[0]?.id });
    setForm({ name: "", agent_id: 0, max_retries: 3, dial_rate: 1 });
    load();
  };

  const setStatus = async (id: number, status: string) => {
    setBusy(id);
    try {
      await updateCampaignStatus(id, status);
      load();
      refreshStats(id);
    } finally {
      setBusy(null);
    }
  };

  const handleDial = async (id: number) => {
    setBusy(id);
    try {
      await dialCampaign(id);
      refreshStats(id);
      load();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(msg || "Dial failed — check outbound SIP trunk in SIP Trunks");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Campaigns</h2>
      </div>
      <Card className="mb-6">
        <CardContent className="py-4">
          <p className="text-sm font-semibold text-slate-700 mb-3">Create New Campaign</p>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600">
                Campaign Name <span className="text-red-500">*</span>
              </label>
              <Input
                placeholder="e.g. May Inverter Drive"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600">
                AI Agent <span className="text-red-500">*</span>
              </label>
              <Select
                value={form.agent_id}
                onChange={(e) => setForm({ ...form, agent_id: Number(e.target.value) })}
              >
                <option value={0}>-- Select Agent --</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600">
                Max Retries
                <span className="text-slate-400 font-normal ml-1">(failed calls retry)</span>
              </label>
              <Input
                type="number"
                placeholder="3"
                min={0}
                max={10}
                value={form.max_retries}
                onChange={(e) => setForm({ ...form, max_retries: Number(e.target.value) })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-600">
                Dial Rate
                <span className="text-slate-400 font-normal ml-1">(calls per batch)</span>
              </label>
              <Input
                type="number"
                placeholder="1"
                min={1}
                max={20}
                value={form.dial_rate}
                onChange={(e) => setForm({ ...form, dial_rate: Number(e.target.value) })}
              />
            </div>
            <Button onClick={handleCreate} className="h-10">
              <Plus className="h-4 w-4 mr-2" /> Create Campaign
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {campaigns.map((c) => {
          const id = c.id as number;
          const st = stats[id];
          const isRunning = (c.status as string) === "running";
          return (
            <Card key={id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div>
                  <h3 className="font-semibold">{c.name as string}</h3>
                  <p className="text-sm text-slate-500">
                    Agent: {agents.find((a) => a.id === (c.agent_id as number))?.name ?? `#${c.agent_id as number}`}
                    {" · "}Dial rate: {c.dial_rate as number}/batch
                    {" · "}Max retries: {c.max_retries as number}
                  </p>
                  {st && (
                    <p className="text-xs text-slate-400 mt-1">
                      Leads: {st.total} total · new: {st.leads?.new ?? 0} · dialing:{" "}
                      {st.leads?.dialing ?? 0}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge status={c.status as string} />
                  {!isRunning && (
                    <Button
                      size="sm"
                      disabled={busy === id}
                      onClick={() => setStatus(id, "running")}
                    >
                      <Play className="h-4 w-4 mr-1" /> Start
                    </Button>
                  )}
                  {isRunning && (
                    <>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={busy === id}
                        onClick={() => setStatus(id, "paused")}
                      >
                        <Pause className="h-4 w-4 mr-1" /> Pause
                      </Button>
                      <Button size="sm" disabled={busy === id} onClick={() => handleDial(id)}>
                        <Phone className="h-4 w-4 mr-1" /> Dial leads now
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-sm text-slate-500 mt-6">
        Upload leads on the <strong>Leads</strong> page and select this campaign. Then{" "}
        <strong>Start</strong> the campaign and click <strong>Dial leads now</strong>. Your phone
        will ring and the AI agent will talk when you answer. Worker and outbound SIP trunk must be
        running.
      </p>
    </div>
  );
}
