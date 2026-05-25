import { useEffect, useState } from "react";
import { Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import {
  applyAllDispatchToLiveKit,
  applyDispatchToLiveKit,
  createDispatchRule,
  deleteDispatchRule,
  getAgents,
  getDispatchRules,
  getSipTrunks,
  syncDispatchFromLiveKit,
  updateDispatchRule,
} from "@/lib/api";

interface DispatchRuleRow {
  id: number;
  agent_id: number;
  rule_type: string;
  match_value: string;
  priority: number;
  sip_trunk_id?: number | null;
  livekit_rule_id?: string | null;
}

export default function Dispatch() {
  const [rules, setRules] = useState<DispatchRuleRow[]>([]);
  const [agents, setAgents] = useState<{ id: number; name: string }[]>([]);
  const [trunks, setTrunks] = useState<{ id: number; name: string }[]>([]);
  const [edits, setEdits] = useState<Record<number, { agent_id: number; sip_trunk_id: number | "" }>>({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [form, setForm] = useState({
    agent_id: 0,
    rule_type: "did",
    match_value: "",
    priority: 0,
    sip_trunk_id: undefined as number | undefined,
  });

  const agentName = (id: number) => agents.find((a) => a.id === id)?.name ?? `Agent #${id}`;

  const load = () => {
    setLoading(true);
    setError("");
    Promise.all([getDispatchRules(), getAgents(), getSipTrunks()])
      .then(([rulesRes, agentsRes, trunksRes]) => {
        const rows = rulesRes.data as DispatchRuleRow[];
        setRules(rows);
        setAgents(agentsRes.data);
        setTrunks(trunksRes.data);
        const next: Record<number, { agent_id: number; sip_trunk_id: number | "" }> = {};
        rows.forEach((r) => {
          next[r.id] = {
            agent_id: r.agent_id,
            sip_trunk_id: r.sip_trunk_id ?? "",
          };
        });
        setEdits(next);
      })
      .catch((e) => setError(e.response?.data?.detail || "Failed to load dispatch rules"))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setSyncMsg("");
    setError("");
    try {
      const { data } = await syncDispatchFromLiveKit();
      setSyncMsg(
        data.error
          ? `Sync error: ${data.error}`
          : `Synced from LiveKit: ${data.created} created, ${data.skipped} skipped`
      );
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const handleCreate = async () => {
    if (!form.agent_id && agents[0]) form.agent_id = agents[0].id;
    if (!form.agent_id) {
      setError("Create an AI agent first");
      return;
    }
    setError("");
    try {
      await createDispatchRule({
        ...form,
        sip_trunk_id: form.sip_trunk_id || undefined,
      });
      setForm({ agent_id: 0, rule_type: "did", match_value: "", priority: 0, sip_trunk_id: undefined });
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Failed to create rule");
    }
  };

  const handleSave = async (ruleId: number, applyLivekit: boolean) => {
    const edit = edits[ruleId];
    if (!edit) return;
    setSavingId(ruleId);
    setError("");
    try {
      await updateDispatchRule(
        ruleId,
        {
          agent_id: edit.agent_id,
          sip_trunk_id: edit.sip_trunk_id === "" ? null : edit.sip_trunk_id,
        },
        applyLivekit
      );
      setSyncMsg(applyLivekit ? "Saved and applied to LiveKit" : "Mapping saved");
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setSavingId(null);
    }
  };

  const handleApplyAllLiveKit = async () => {
    setSyncing(true);
    setError("");
    try {
      const { data } = await applyAllDispatchToLiveKit();
      const ok = (data.applied as string[])?.length ?? 0;
      const bad = (data.errors as string[])?.length ?? 0;
      setSyncMsg(`Applied ${ok} rule(s) to LiveKit` + (bad ? ` (${bad} failed)` : ""));
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Apply all failed");
    } finally {
      setSyncing(false);
    }
  };

  const handleApplyLiveKit = async (ruleId: number) => {
    setSavingId(ruleId);
    setError("");
    try {
      const { data } = await applyDispatchToLiveKit(ruleId);
      setSyncMsg(data.message || "Applied to LiveKit");
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Apply to LiveKit failed");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h2 className="text-2xl font-bold">Dispatch Rules</h2>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={handleApplyAllLiveKit} disabled={syncing}>
            Apply all to LiveKit
          </Button>
          <Button variant="secondary" onClick={handleSync} disabled={syncing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${syncing ? "animate-spin" : ""}`} />
            Sync from LiveKit
          </Button>
        </div>
      </div>

      <p className="text-sm text-slate-500 mb-4">
        Map each inbound <strong>DID</strong> (your business number) to an AI agent. Worker must register
        as <strong>vbots</strong> (<code>LIVEKIT_AGENT_NAME</code> in .env). After changes, click{" "}
        <strong>Apply all to LiveKit</strong> so inbound calls dispatch to the worker.
      </p>

      {error && <div className="mb-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 text-sm">{error}</div>}
      {syncMsg && (
        <div className="mb-4 rounded-lg bg-green-50 text-green-800 px-4 py-3 text-sm">{syncMsg}</div>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Add new rule</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Select value={form.rule_type} onChange={(e) => setForm({ ...form, rule_type: e.target.value })}>
            <option value="did">DID</option>
            <option value="trunk">Trunk</option>
            <option value="campaign">Campaign</option>
            <option value="ingroup">Ingroup</option>
          </Select>
          <Input
            placeholder={form.rule_type === "did" ? "Your DID e.g. 911204646549" : "Trunk ID or name"}
            value={form.match_value}
            onChange={(e) => setForm({ ...form, match_value: e.target.value })}
          />
          <Select value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: Number(e.target.value) })}>
            <option value={0}>Select Agent</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <Select
            value={form.sip_trunk_id ?? ""}
            onChange={(e) =>
              setForm({ ...form, sip_trunk_id: e.target.value ? Number(e.target.value) : undefined })
            }
          >
            <option value="">SIP Trunk (optional)</option>
            {trunks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Button onClick={handleCreate} className="lg:col-span-2">
            <Plus className="h-4 w-4 mr-2" /> Add Rule
          </Button>
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-slate-500">Loading...</p>
      ) : rules.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-slate-500">
            No dispatch rules yet. Sync from LiveKit or add a rule above.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {rules.map((r) => {
            const edit = edits[r.id] ?? { agent_id: r.agent_id, sip_trunk_id: r.sip_trunk_id ?? "" };
            const busy = savingId === r.id;
            return (
              <Card key={r.id}>
                <CardContent className="py-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium text-sm">
                        <span className="uppercase text-brand-700">{r.rule_type}</span> →{" "}
                        <span className="font-mono">{r.match_value}</span>
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        Currently: {agentName(r.agent_id)}
                        {r.livekit_rule_id && (
                          <span className="block font-mono text-slate-400">
                            LiveKit: {r.livekit_rule_id}
                          </span>
                        )}
                      </p>
                    </div>
                    <Button variant="danger" size="sm" onClick={() => deleteDispatchRule(r.id).then(load)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
                    <div>
                      <label className="text-xs text-slate-500 block mb-1">AI Agent</label>
                      <Select
                        value={edit.agent_id}
                        onChange={(e) =>
                          setEdits((prev) => ({
                            ...prev,
                            [r.id]: { ...edit, agent_id: Number(e.target.value) },
                          }))
                        }
                      >
                        {agents.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <div>
                      <label className="text-xs text-slate-500 block mb-1">SIP Trunk</label>
                      <Select
                        value={edit.sip_trunk_id}
                        onChange={(e) =>
                          setEdits((prev) => ({
                            ...prev,
                            [r.id]: {
                              ...edit,
                              sip_trunk_id: e.target.value === "" ? "" : Number(e.target.value),
                            },
                          }))
                        }
                      >
                        <option value="">None</option>
                        {trunks.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => handleSave(r.id, false)}>
                        <Save className="h-4 w-4 mr-1" /> Save
                      </Button>
                      <Button size="sm" disabled={busy} onClick={() => handleSave(r.id, true)}>
                        Save + LiveKit
                      </Button>
                      <Button size="sm" variant="secondary" disabled={busy} onClick={() => handleApplyLiveKit(r.id)}>
                        Apply to LiveKit
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
