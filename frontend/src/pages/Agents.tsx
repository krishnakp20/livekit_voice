import { useEffect, useState } from "react";
import { Pencil, Plus, Trash2, TestTube, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { createAgent, deleteAgent, getAgents, testAgent, updateAgent } from "@/lib/api";

interface Agent {
  id: number;
  name: string;
  language: string;
  voice: string;
  provider: string;
  model: string;
  prompt: string;
  greeting: string;
  fallback_message: string;
  temperature: number;
  max_tokens: number;
  transfer_enabled: boolean;
  transfer_number: string | null;
  data_fields_json: string | null;
  required_lead_fields: string | null;
  webhook_json: string | null;
  gender: string;
  is_active: boolean;
  stt_provider: string | null;
  stt_api_key: string | null;   // masked ("••••••••") when set, never the real key
  llm_provider: string | null;
  llm_api_key: string | null;   // masked
  tts_provider: string | null;
  tts_api_key: string | null;   // masked
}

/** Curated, voice-latency-appropriate models per LLM provider (per-agent dropdown). */
const LLM_MODELS: Record<string, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano"],
  groq: ["llama-3.3-70b-versatile"],
  openai_realtime: ["gpt-realtime", "gpt-realtime-1.5", "gpt-realtime-2"],
};

/** "key: description" per line  ⇄  JSON [{key, description}] */
function fieldsToText(json: string | null | undefined): string {
  if (!json) return "";
  try {
    const arr = JSON.parse(json);
    if (!Array.isArray(arr)) return "";
    return arr.map((f) => `${f.key}: ${f.description || ""}`).join("\n");
  } catch {
    return "";
  }
}
function textToFieldsJson(text: string): string {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const arr = lines.map((l) => {
    const idx = l.indexOf(":");
    const key = (idx === -1 ? l : l.slice(0, idx)).trim().replace(/\s+/g, "_").toLowerCase();
    const description = idx === -1 ? l : l.slice(idx + 1).trim();
    return { key, description };
  });
  return JSON.stringify(arr);
}

type AgentForm = {
  name: string;
  language: string;
  voice: string;
  model: string;
  prompt: string;
  greeting: string;
  fallback_message: string;
  temperature: number;
  max_tokens: number;
  transfer_enabled: boolean;
  transfer_number: string;
  data_fields_text: string;
  required_lead_fields: string;
  webhook_url: string;
  webhook_headers: string;
  webhook_template: string;
  gender: string;
  // Explicit provider overrides — blank = use the server's default (today's
  // behaviour). *_api_key holds a NEWLY TYPED plaintext key for this edit
  // session only; it is never pre-filled from the masked stored value.
  stt_provider: string;
  stt_api_key: string;
  stt_key_is_set: boolean;   // true if the server reports one already stored
  llm_provider: string;
  llm_api_key: string;
  llm_key_is_set: boolean;
  tts_provider: string;
  tts_api_key: string;
  tts_key_is_set: boolean;
};

const defaultForm: AgentForm = {
  name: "",
  language: "hi-en",
  voice: "simran",
  gender: "female",
  model: "gpt-4o-mini",
  prompt: "You are a friendly Indian sales agent.",
  greeting: "Namaste! Kaise madad kar sakti hoon?",
  fallback_message: "Maaf kijiye, dobara batayenge?",
  temperature: 0.6,
  max_tokens: 120,
  transfer_enabled: false,
  transfer_number: "",
  data_fields_text: "name: customer full name\nphone: contact number\ncity: city and state\ncapacity: required inverter capacity\nusage: home / shop / office / factory",
  required_lead_fields: "",
  webhook_url: "",
  webhook_headers: "",
  webhook_template: "",
  stt_provider: "",
  stt_api_key: "",
  stt_key_is_set: false,
  llm_provider: "",
  llm_api_key: "",
  llm_key_is_set: false,
  tts_provider: "",
  tts_api_key: "",
  tts_key_is_set: false,
};

/** ai_agents.webhook_json  ⇄  the three UI fields */
function webhookToForm(json: string | null | undefined) {
  try {
    const cfg = JSON.parse(json || "{}");
    return {
      webhook_url: cfg.url || "",
      webhook_headers: cfg.headers ? JSON.stringify(cfg.headers, null, 2) : "",
      webhook_template: cfg.payload_template
        ? JSON.stringify(cfg.payload_template, null, 2)
        : "",
    };
  } catch {
    return { webhook_url: "", webhook_headers: "", webhook_template: "" };
  }
}

function agentToForm(agent: Agent): AgentForm {
  return {
    name: agent.name,
    language: agent.language,
    voice: agent.voice,
    gender: agent.gender ?? "female",
    model: agent.model,
    prompt: agent.prompt,
    greeting: agent.greeting,
    fallback_message: agent.fallback_message,
    temperature: agent.temperature,
    max_tokens: agent.max_tokens,
    transfer_enabled: agent.transfer_enabled ?? false,
    transfer_number: agent.transfer_number ?? "",
    data_fields_text: fieldsToText(agent.data_fields_json),
    required_lead_fields: agent.required_lead_fields ?? "",
    ...webhookToForm(agent.webhook_json),
    stt_provider: agent.stt_provider ?? "",
    stt_api_key: "",   // never pre-fill a real key from the masked value
    stt_key_is_set: !!agent.stt_api_key,
    llm_provider: agent.llm_provider ?? "",
    llm_api_key: "",
    llm_key_is_set: !!agent.llm_api_key,
    tts_provider: agent.tts_provider ?? "",
    tts_api_key: "",
    tts_key_is_set: !!agent.tts_api_key,
  };
}

function AgentFormFields({
  form,
  setForm,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  form: AgentForm;
  setForm: (f: AgentForm) => void;
  submitLabel: string;
  onSubmit: () => void;
  onCancel?: () => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Input
        placeholder="Agent Name"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
      />
      <Select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
        <option value="en-IN">English</option>
        <option value="hi-IN">Hindi</option>
        <option value="hi-en">Hinglish</option>
      </Select>
      <div>
        <label className="text-xs font-medium text-slate-500 mb-1 block">Voice</label>
        <Input
          placeholder={
            form.llm_provider === "openai_realtime"
              ? "Realtime voice name (e.g. marin, alloy, cedar)"
              : "Cartesia voice ID (UUID) or Sarvam name (e.g. simran)"
          }
          value={form.voice}
          onChange={(e) => setForm({ ...form, voice: e.target.value })}
        />
        <p className="mt-1 text-xs text-slate-400">
          {form.llm_provider === "openai_realtime"
            ? "OpenAI Realtime voice name — see platform.openai.com/docs for the current list (e.g. marin, alloy, cedar)."
            : <>Paste a Cartesia voice UUID from cartesia.ai/voices for a custom voice — e.g. a
              British-English voice for a UK client. Leave a name like <code>simran</code> for the default.</>}
        </p>
      </div>
      <Select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
        <option value="female">Female (uses feminine Hindi grammar)</option>
        <option value="male">Male (uses masculine Hindi grammar)</option>
      </Select>
      <Input
        placeholder="Model (e.g. gpt-4o-mini)"
        value={form.model}
        onChange={(e) => setForm({ ...form, model: e.target.value })}
      />

      <div className="md:col-span-2 border-t border-slate-200 pt-3">
        <label className="text-sm text-slate-700">Explicit provider overrides (optional)</label>
        <p className="mb-2 text-xs text-slate-400">
          Leave any of these on "Default" to use the server's standard setup. Pin an
          explicit provider when a client brings their own API key (e.g. their own
          ElevenLabs or Cartesia account).
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className={form.llm_provider === "openai_realtime" ? "opacity-40" : undefined}>
            <label className="text-xs font-medium text-slate-500 mb-1 block">STT Provider</label>
            <Select
              value={form.stt_provider}
              disabled={form.llm_provider === "openai_realtime"}
              onChange={(e) => setForm({ ...form, stt_provider: e.target.value })}
            >
              <option value="">Default</option>
              <option value="deepgram">Deepgram</option>
              <option value="sarvam">Sarvam</option>
            </Select>
            <Input
              type="password"
              className="mt-2"
              disabled={form.llm_provider === "openai_realtime"}
              placeholder={form.stt_key_is_set ? "Key is set — enter to replace" : "API key (optional)"}
              value={form.stt_api_key}
              onChange={(e) => setForm({ ...form, stt_api_key: e.target.value })}
            />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">LLM Provider</label>
            <Select
              value={form.llm_provider}
              onChange={(e) => {
                const provider = e.target.value;
                const models = LLM_MODELS[provider];
                setForm({ ...form, llm_provider: provider, model: models ? models[0] : form.model });
              }}
            >
              <option value="">Default</option>
              <option value="openai">OpenAI</option>
              <option value="groq">Groq</option>
              <option value="openai_realtime">OpenAI Realtime (Speech-to-Speech)</option>
            </Select>
            {form.llm_provider === "openai_realtime" && (
              <p className="mt-1 text-xs text-slate-400">
                Speech-to-speech: one model handles listening, thinking, and speaking directly —
                the STT and TTS providers on the right are ignored for this agent.
              </p>
            )}
            {form.llm_provider && LLM_MODELS[form.llm_provider] && (
              <Select
                className="mt-2"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
              >
                {LLM_MODELS[form.llm_provider].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </Select>
            )}
            <Input
              type="password"
              className="mt-2"
              placeholder={form.llm_key_is_set ? "Key is set — enter to replace" : "API key (optional)"}
              value={form.llm_api_key}
              onChange={(e) => setForm({ ...form, llm_api_key: e.target.value })}
            />
          </div>

          <div className={form.llm_provider === "openai_realtime" ? "opacity-40" : undefined}>
            <label className="text-xs font-medium text-slate-500 mb-1 block">TTS Provider</label>
            <Select
              value={form.tts_provider}
              disabled={form.llm_provider === "openai_realtime"}
              onChange={(e) => setForm({ ...form, tts_provider: e.target.value })}
            >
              <option value="">Default</option>
              <option value="cartesia">Cartesia</option>
              <option value="sarvam">Sarvam</option>
              <option value="elevenlabs">ElevenLabs</option>
            </Select>
            <p className="mt-1 text-xs text-slate-400">Uses the Voice field above as the voice ID.</p>
            <Input
              type="password"
              className="mt-2"
              disabled={form.llm_provider === "openai_realtime"}
              placeholder={form.tts_key_is_set ? "Key is set — enter to replace" : "API key (optional)"}
              value={form.tts_api_key}
              onChange={(e) => setForm({ ...form, tts_api_key: e.target.value })}
            />
          </div>
        </div>
      </div>

      <div className="md:col-span-2">
        <label className="text-xs font-medium text-slate-500 mb-1 block">System prompt</label>
        <Textarea
          rows={12}
          className="min-h-[200px] font-mono text-xs"
          placeholder="System Prompt — scripts, SOP, renewal flow, etc."
          value={form.prompt}
          onChange={(e) => setForm({ ...form, prompt: e.target.value })}
        />
      </div>
      <div className="md:col-span-2">
        <label className="text-xs font-medium text-slate-500 mb-1 block">Greeting (first thing caller hears)</label>
        <Textarea
          rows={3}
          value={form.greeting}
          onChange={(e) => setForm({ ...form, greeting: e.target.value })}
        />
      </div>
      <Input
        placeholder="Fallback Message"
        value={form.fallback_message}
        onChange={(e) => setForm({ ...form, fallback_message: e.target.value })}
      />
      <div className="flex gap-4">
        <div className="flex-1">
          <label className="text-xs text-slate-500">Temperature</label>
          <Input
            type="number"
            step="0.1"
            min={0}
            max={2}
            value={form.temperature}
            onChange={(e) => setForm({ ...form, temperature: parseFloat(e.target.value) || 0.6 })}
          />
        </div>
        <div className="flex-1">
          <label className="text-xs text-slate-500">Max tokens</label>
          <Input
            type="number"
            min={50}
            max={500}
            value={form.max_tokens}
            onChange={(e) => setForm({ ...form, max_tokens: parseInt(e.target.value, 10) || 120 })}
          />
        </div>
      </div>
      <div className="md:col-span-2 border-t border-slate-200 pt-3">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={form.transfer_enabled}
            onChange={(e) => setForm({ ...form, transfer_enabled: e.target.checked })}
          />
          Enable call transfer to a human agent
        </label>
        {form.transfer_enabled && (
          <div className="mt-2">
            <label className="text-xs text-slate-500">
              Transfer phone number (E.164, e.g. +919911362206)
            </label>
            <Input
              type="tel"
              placeholder="+919911362206"
              value={form.transfer_number}
              onChange={(e) => setForm({ ...form, transfer_number: e.target.value })}
            />
            <p className="mt-1 text-xs text-slate-400">
              The bot transfers here when the customer asks for a human, is
              frustrated, or asks something outside its scope.
            </p>
          </div>
        )}
      </div>
      <div className="md:col-span-2 border-t border-slate-200 pt-3">
        <label className="text-sm text-slate-700">Data to collect from the call</label>
        <p className="mb-1 text-xs text-slate-400">
          One field per line, format <code>key: description</code>. The bot asks for
          these during the call and they're auto-extracted from the transcript afterwards.
        </p>
        <Textarea
          rows={5}
          placeholder={"name: customer full name\nphone: contact number\ncity: city and state"}
          value={form.data_fields_text}
          onChange={(e) => setForm({ ...form, data_fields_text: e.target.value })}
        />
      </div>
      <div className="md:col-span-2 border-t border-slate-200 pt-3">
        <label className="text-sm text-slate-700">Required lead fields (outbound)</label>
        <p className="mb-1 text-xs text-slate-400">
          Comma-separated CSV column names that MUST be present for each lead, e.g.{" "}
          <code>customer_name, current_plan_name, current_plan_fee, whatsapp_link</code>.
          Leads missing any of these are skipped at dial time. Use the <code>{"{token}"}</code>{" "}
          names from your prompt. Leave blank to dial every lead.
        </p>
        <Input
          placeholder="customer_name, current_plan_name, whatsapp_link"
          value={form.required_lead_fields}
          onChange={(e) => setForm({ ...form, required_lead_fields: e.target.value })}
        />
      </div>
      <div className="md:col-span-2 border-t border-slate-200 pt-3">
        <label className="text-sm text-slate-700">CRM webhook (optional)</label>
        <p className="mb-1 text-xs text-slate-400">
          If a URL is set, the data collected on each call is POSTed here after the call ends.
        </p>
        <Input
          placeholder="https://crmapi.example.com/bot/webhook-api"
          value={form.webhook_url}
          onChange={(e) => setForm({ ...form, webhook_url: e.target.value })}
        />
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">
              Request headers (JSON)
            </label>
            <Textarea
              rows={5}
              placeholder={'{\n  "Content-Type": "application/json",\n  "Auth-Token": "..."\n}'}
              value={form.webhook_headers}
              onChange={(e) => setForm({ ...form, webhook_headers: e.target.value })}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">
              Request data template (JSON)
            </label>
            <Textarea
              rows={5}
              placeholder={'{\n  "Calling Phone no.": "",\n  "City ": "",\n  "PIN": ""\n}'}
              value={form.webhook_template}
              onChange={(e) => setForm({ ...form, webhook_template: e.target.value })}
            />
            <p className="mt-1 text-xs text-slate-400">
              Paste the CRM's Request Data exactly. Its field names are kept as-is and
              filled from the collected data.
            </p>
          </div>
        </div>
      </div>
      <div className="md:col-span-2 flex gap-2">
        <Button onClick={onSubmit}>{submitLabel}</Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            <X className="h-4 w-4 mr-1" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [createForm, setCreateForm] = useState<AgentForm>(defaultForm);
  const [editForm, setEditForm] = useState<AgentForm>(defaultForm);
  const [testResult, setTestResult] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => getAgents().then((r) => setAgents(r.data));

  useEffect(() => {
    load();
  }, []);

  const toPayload = (form: AgentForm) => {
    const {
      data_fields_text,
      required_lead_fields,
      webhook_url,
      webhook_headers,
      webhook_template,
      stt_provider,
      stt_api_key,
      stt_key_is_set: _stt_key_is_set,
      llm_provider,
      llm_api_key,
      llm_key_is_set: _llm_key_is_set,
      tts_provider,
      tts_api_key,
      tts_key_is_set: _tts_key_is_set,
      ...rest
    } = form;

    // Assemble the three webhook inputs into ai_agents.webhook_json.
    // Throws on malformed JSON so the user gets told instead of silently losing it.
    let webhook_json: string | null = null;
    if (webhook_url.trim()) {
      const cfg: Record<string, unknown> = { url: webhook_url.trim() };
      if (webhook_headers.trim()) {
        try {
          cfg.headers = JSON.parse(webhook_headers);
        } catch {
          throw new Error("Webhook request headers must be valid JSON.");
        }
      }
      if (webhook_template.trim()) {
        try {
          cfg.payload_template = JSON.parse(webhook_template);
        } catch {
          throw new Error("Webhook request data template must be valid JSON.");
        }
      }
      webhook_json = JSON.stringify(cfg);
    }

    return {
      ...rest,
      data_fields_json: textToFieldsJson(data_fields_text),
      required_lead_fields: required_lead_fields.trim() || null,
      webhook_json,
      stt_provider: stt_provider.trim() || null,
      llm_provider: llm_provider.trim() || null,
      tts_provider: tts_provider.trim() || null,
      // Only include *_api_key if the user actually typed a NEW key this
      // session. Omitting it (rather than sending "") means the backend's
      // exclude_unset leaves whatever key is already stored untouched.
      ...(stt_api_key.trim() ? { stt_api_key: stt_api_key.trim() } : {}),
      ...(llm_api_key.trim() ? { llm_api_key: llm_api_key.trim() } : {}),
      ...(tts_api_key.trim() ? { tts_api_key: tts_api_key.trim() } : {}),
    };
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      await createAgent(toPayload(createForm));
      setShowCreate(false);
      setCreateForm(defaultForm);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not save agent.");
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (agent: Agent) => {
    setShowCreate(false);
    setEditingId(agent.id);
    setEditForm(agentToForm(agent));
    setTestResult("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(defaultForm);
  };

  const handleSaveEdit = async () => {
    if (editingId == null) return;
    setSaving(true);
    try {
      await updateAgent(editingId, toPayload(editForm));
      setEditingId(null);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Could not save agent.");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (id: number, name: string) => {
    const { data } = await testAgent(id, "Namaste, main renewal ke baare mein poochhna chahta hoon");
    setTestResult(`${name}: ${data.response} (${data.latency_ms}ms)`);
  };

  const toggleActive = async (agent: Agent) => {
    await updateAgent(agent.id, { is_active: !agent.is_active });
    load();
  };

  const handleDelete = async (agent: Agent) => {
    if (!confirm(`Delete agent "${agent.name}"? This cannot be undone.`)) return;
    if (editingId === agent.id) cancelEdit();
    await deleteAgent(agent.id);
    load();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">AI Agents</h2>
        <Button
          onClick={() => {
            setShowCreate(!showCreate);
            setEditingId(null);
          }}
        >
          <Plus className="h-4 w-4 mr-2" /> New Agent
        </Button>
      </div>

      <p className="text-sm text-slate-500 mb-4">
        Click <strong>Edit</strong> on an agent to change prompt, greeting, voice, and language. Use agent{" "}
        <strong>ID</strong> in Dispatch and Campaigns. Changes apply to the next call (restart worker if a call is
        already in progress).
      </p>

      {showCreate && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Create AI Agent</CardTitle>
          </CardHeader>
          <CardContent>
            <AgentFormFields
              form={createForm}
              setForm={setCreateForm}
              submitLabel={saving ? "Saving…" : "Create Agent"}
              onSubmit={handleCreate}
              onCancel={() => {
                setShowCreate(false);
                setCreateForm(defaultForm);
              }}
            />
          </CardContent>
        </Card>
      )}

      {testResult && (
        <Card className="mb-4 border-brand-200 bg-brand-50">
          <CardContent className="py-3 text-sm whitespace-pre-wrap">{testResult}</CardContent>
        </Card>
      )}

      <div className="grid gap-4">
        {agents.map((agent) => (
          <Card key={agent.id}>
            {editingId === agent.id ? (
              <CardContent className="pt-6">
                <CardTitle className="text-lg mb-4">
                  Edit agent — {agent.name} <span className="text-slate-400 font-normal">#{agent.id}</span>
                </CardTitle>
                <AgentFormFields
                  form={editForm}
                  setForm={setEditForm}
                  submitLabel={saving ? "Saving…" : "Save changes"}
                  onSubmit={handleSaveEdit}
                  onCancel={cancelEdit}
                />
              </CardContent>
            ) : (
              <CardContent className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{agent.name}</h3>
                    <span className="text-xs font-mono text-slate-400">ID #{agent.id}</span>
                    <Badge status={agent.is_active ? "active" : "inactive"} />
                  </div>
                  <p className="text-sm text-slate-500 mt-1">
                    {agent.language} · {agent.voice} · {agent.model}
                  </p>
                  <p className="text-sm text-slate-400 mt-1 italic line-clamp-2">"{agent.greeting}"</p>
                </div>

                <div className="flex flex-wrap items-center gap-2 shrink-0">
                  <Button variant="secondary" size="sm" onClick={() => startEdit(agent)}>
                    <Pencil className="h-4 w-4 mr-1" />
                    Edit
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => toggleActive(agent)}>
                    {agent.is_active ? "Deactivate" : "Activate"}
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => handleTest(agent.id, agent.name)}>
                    <TestTube className="h-4 w-4 mr-1" />
                    Test
                  </Button>
                  <Button variant="danger" size="sm" onClick={() => handleDelete(agent)}>
                    <Trash2 className="h-4 w-4 mr-1" />
                    Delete
                  </Button>
                </div>
              </CardContent>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
