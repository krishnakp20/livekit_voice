import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/layout/Layout";
import Login from "@/pages/Login";
import ResetPassword from "@/pages/ResetPassword";
import Dashboardold from "@/pages/Dashboard_old";
import Dashboard from "@/pages/Dashboard";
import Agents from "@/pages/Agents";
import SipTrunks from "@/pages/SipTrunks";
import Dispatch from "@/pages/Dispatch";
import Campaigns from "@/pages/Campaigns";
import Leads from "@/pages/Leads";
import LiveCalls from "@/pages/LiveCalls";
import Calls from "@/pages/Calls";
import Analytics from "@/pages/Analytics";
import Billing from "@/pages/Billing";
import WhatsApp from "@/pages/WhatsApp";
import Integrations from "@/pages/Integrations";
import ApiKeys from "@/pages/ApiKeys";
import Settings from "@/pages/Settings";
import Clients from "@/pages/Clients";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Loading...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="dashboard_old" element={<Dashboardold />} />
            <Route path="clients" element={<Clients />} />
            <Route path="agents" element={<Agents />} />
            <Route path="sip-trunks" element={<SipTrunks />} />
            <Route path="phone-numbers" element={<SipTrunks />} />
            <Route path="reports" element={<Analytics />} />
            <Route path="dispatch" element={<Dispatch />} />
            <Route path="campaigns" element={<Campaigns />} />
            <Route path="leads" element={<Leads />} />
            <Route path="live-calls" element={<LiveCalls />} />
            <Route path="calls" element={<Calls />} />
            <Route path="analytics" element={<Analytics />} />
            <Route path="billing" element={<Billing />} />
            <Route path="whatsapp" element={<WhatsApp />} />
            <Route path="integrations" element={<Integrations />} />
            <Route path="api-keys" element={<ApiKeys />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider> 
  );
}
