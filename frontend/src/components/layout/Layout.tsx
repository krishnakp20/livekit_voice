import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Sidebar } from "./Sidebar";
import { useAuth } from "@/context/AuthContext";
import { getClients } from "@/lib/api";

interface ClientOpt {
  id: number;
  name: string;
}

/** Super-admin only: pick which client's data the whole app shows. */
function ClientSwitcher() {
  const { user } = useAuth();
  const [clients, setClients] = useState<ClientOpt[]>([]);
  const active = localStorage.getItem("active_client_id") || "";

  useEffect(() => {
    if (user?.role === "super_admin") {
      getClients()
        .then((r) => setClients(r.data))
        .catch(() => setClients([]));
    }
  }, [user]);

  if (user?.role !== "super_admin") return null;

  const onChange = (value: string) => {
    if (value) localStorage.setItem("active_client_id", value);
    else localStorage.removeItem("active_client_id");
    // Reload so every page refetches in the selected client's context.
    window.location.reload();
  };

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-amber-600">SUPER ADMIN</span>
      <select
        value={active}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 px-2 py-1 text-sm"
      >
        <option value="">— Select client —</option>
        {clients.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Layout() {
  const navigate = useNavigate();

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("active_client_id");
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Sidebar />
      <div className="pl-60">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur px-8">
          <h1 className="text-sm text-slate-500">AI Voice Calling Platform</h1>
          <div className="flex items-center gap-4">
            <ClientSwitcher />
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </header>
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
