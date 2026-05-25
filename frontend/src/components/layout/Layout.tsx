import { LogOut } from "lucide-react";
import { Outlet, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const navigate = useNavigate();

  const logout = () => {
    localStorage.removeItem("access_token");
    navigate("/login");
  };

  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur px-8">
          <h1 className="text-sm text-slate-500">AI Voice Calling Platform</h1>
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </header>
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
