import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "/api/v1";

const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

function clearAuthAndRedirect() {
  localStorage.removeItem("access_token");
  if (!window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status;
    if (status === 401 || status === 403) {
      clearAuthAndRedirect();
    }
    return Promise.reject(err);
  }
);

export default api;

// Auth
export const login = (email: string, password: string) =>
  api.post("/auth/login", { email, password });

export const getMe = () => api.get("/auth/me");

// Agents
export const getAgents = () => api.get("/agents");
export const createAgent = (data: Record<string, unknown>) => api.post("/agents", data);
export const updateAgent = (id: number, data: Record<string, unknown>) =>
  api.patch(`/agents/${id}`, data);
export const deleteAgent = (id: number) => api.delete(`/agents/${id}`);
export const testAgent = (id: number, message: string) =>
  api.post(`/agents/${id}/test`, { message });

// SIP
export const getSipTrunks = () => api.get("/sip-trunks");
export const createSipTrunk = (data: Record<string, unknown>) => api.post("/sip-trunks", data);
export const syncSipTrunksFromLiveKit = () => api.post("/sip-trunks/sync-from-livekit");
export const testSipTrunk = (id: number) => api.post(`/sip-trunks/${id}/test`);

// Dispatch
export const getDispatchRules = () => api.get("/dispatch");
export const createDispatchRule = (data: Record<string, unknown>) => api.post("/dispatch", data);
export const updateDispatchRule = (
  id: number,
  data: Record<string, unknown>,
  applyLivekit = false
) => api.patch(`/dispatch/${id}`, data, { params: applyLivekit ? { apply_livekit: true } : {} });
export const applyDispatchToLiveKit = (id: number) => api.post(`/dispatch/${id}/apply-livekit`);
export const applyAllDispatchToLiveKit = () => api.post("/dispatch/apply-all-livekit");
export const syncDispatchFromLiveKit = () => api.post("/dispatch/sync-from-livekit");
export const deleteDispatchRule = (id: number) => api.delete(`/dispatch/${id}`);

// Campaigns & Leads
export const getCampaigns = () => api.get("/campaigns");
export const createCampaign = (data: Record<string, unknown>) => api.post("/campaigns", data);
export const updateCampaignStatus = (id: number, status: string) =>
  api.patch(`/campaigns/${id}/status`, { status });
export const dialCampaign = (id: number, limit?: number) =>
  api.post(`/campaigns/${id}/dial`, null, { params: limit != null ? { limit } : {} });
export const getCampaignStats = (id: number) => api.get(`/campaigns/${id}/stats`);
export const getLeads = (campaignId?: number) =>
  api.get("/leads", { params: campaignId ? { campaign_id: campaignId } : {} });
export const uploadLeads = (file: File, campaignId?: number) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/leads/upload", form, {
    params: campaignId ? { campaign_id: campaignId } : {},
    headers: { "Content-Type": "multipart/form-data" },
  });
};

// Calls
export const getCalls = () => api.get("/calls");
export const getLiveCalls = () => api.get("/calls/live");
export const getCall = (id: number) => api.get(`/calls/${id}`);

/** Authenticated fetch — required because <audio src> cannot send Bearer tokens. */
export const fetchCallRecordingBlob = (callId: number) =>
  api.get(`/calls/${callId}/recording/file`, { responseType: "blob" });

// Analytics
export const getDashboardStats = (days = 30) =>
  api.get("/analytics/dashboard", { params: { days } });
export const getAgentPerformance = (days = 30) =>
  api.get("/analytics/agents", { params: { days } });

// Integrations & WhatsApp
export const getIntegrations = () => api.get("/integrations");
export const createIntegration = (data: Record<string, unknown>) =>
  api.post("/integrations", data);
export const getWhatsAppLogs = () => api.get("/whatsapp/logs");
