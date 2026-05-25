import { useEffect, useState } from "react";
import { Plus, RefreshCw, TestTube } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { createSipTrunk, getSipTrunks, syncSipTrunksFromLiveKit, testSipTrunk } from "@/lib/api";

export default function SipTrunks() {
  const [trunks, setTrunks] = useState<Record<string, unknown>[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [syncMsg, setSyncMsg] = useState("");
  const [form, setForm] = useState({
    name: "",
    direction: "inbound",
    sip_uri: "",
    auth_username: "",
    auth_password: "",
    did_numbers: "",
  });

  const load = () => {
    setLoading(true);
    setError("");
    getSipTrunks()
      .then((r) => setTrunks(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Failed to load trunks"))
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
      const { data } = await syncSipTrunksFromLiveKit();
      setSyncMsg(
        data.error
          ? `Sync error: ${data.error}`
          : `Synced from LiveKit: ${data.created} created, ${data.updated} updated`
      );
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Sync failed — check LiveKit URL and API keys in .env");
    } finally {
      setSyncing(false);
    }
  };

  const handleCreate = async () => {
    setError("");
    try {
      await createSipTrunk(form);
      setShowForm(false);
      setForm({ name: "", direction: "inbound", sip_uri: "", auth_username: "", auth_password: "", did_numbers: "" });
      load();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || "Failed to create trunk");
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h2 className="text-2xl font-bold">SIP Trunks</h2>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={handleSync} disabled={syncing}>
            <RefreshCw className={`h-4 w-4 mr-2 ${syncing ? "animate-spin" : ""}`} />
            Sync from LiveKit
          </Button>
          <Button onClick={() => setShowForm(!showForm)}>
            <Plus className="h-4 w-4 mr-2" /> New Trunk
          </Button>
        </div>
      </div>

      <p className="text-sm text-slate-500 mb-4">
        VBots only shows trunks saved in its database. Trunks created in the LiveKit console must be synced with the button above, or created here via &quot;New Trunk&quot;.
      </p>

      {error && <div className="mb-4 rounded-lg bg-red-50 text-red-700 px-4 py-3 text-sm">{error}</div>}
      {syncMsg && <div className="mb-4 rounded-lg bg-green-50 text-green-800 px-4 py-3 text-sm">{syncMsg}</div>}

      {showForm && (
        <Card className="mb-6">
          <CardHeader><CardTitle>Create SIP Trunk</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="inbound">Inbound</option>
              <option value="outbound">Outbound</option>
            </Select>
            <Input placeholder="SIP URI" value={form.sip_uri} onChange={(e) => setForm({ ...form, sip_uri: e.target.value })} />
            <Input placeholder="DID Numbers (comma-separated)" value={form.did_numbers} onChange={(e) => setForm({ ...form, did_numbers: e.target.value })} />
            <Input placeholder="Auth Username" value={form.auth_username} onChange={(e) => setForm({ ...form, auth_username: e.target.value })} />
            <Input placeholder="Auth Password" type="password" value={form.auth_password} onChange={(e) => setForm({ ...form, auth_password: e.target.value })} />
            <Button onClick={handleCreate} className="md:col-span-2">Create Trunk</Button>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-slate-500">Loading...</p>
      ) : trunks.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-slate-500">
            No SIP trunks in VBots yet. Click <strong>Sync from LiveKit</strong> if you already created trunks there.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {trunks.map((t) => (
            <Card key={t.id as number}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <h3 className="font-semibold">{t.name as string}</h3>
                  <p className="text-sm text-slate-500">
                    {(t.direction as string)?.toLowerCase()} · {t.sip_uri as string}
                  </p>
                  {!!t.did_numbers && <p className="text-xs text-slate-400">DIDs: {t.did_numbers as string}</p>}
                  {!!t.livekit_trunk_id && (
                    <p className="text-xs text-slate-400 font-mono">LiveKit: {t.livekit_trunk_id as string}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge status={(t.status as string)?.toLowerCase()} />
                  <Button variant="secondary" size="sm" onClick={() => testSipTrunk(t.id as number).then(load)}>
                    <TestTube className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
