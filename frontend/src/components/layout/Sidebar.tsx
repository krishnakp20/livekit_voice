import { cn } from "@/lib/utils";
import {
  BarChart3,
  Bot,
  CreditCard,
  GitBranch,
  Key,
  LayoutDashboard,
  MessageSquare,
  Phone,
  PhoneCall,
  Radio,
  Settings,
  Target,
  Users,
  Webhook,
} from "lucide-react";
import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/agents", icon: Bot, label: "AI Agents" },
  { to: "/sip-trunks", icon: Radio, label: "SIP Trunks" },
  { to: "/dispatch", icon: GitBranch, label: "Dispatch Rules" },
  { to: "/campaigns", icon: Target, label: "Campaigns" },
  { to: "/leads", icon: Users, label: "Leads" },
  { to: "/live-calls", icon: PhoneCall, label: "Live Calls" },
  { to: "/calls", icon: Phone, label: "Call History" },
  { to: "/analytics", icon: BarChart3, label: "Analytics" },
  { to: "/billing", icon: CreditCard, label: "Billing" },
  { to: "/whatsapp", icon: MessageSquare, label: "WhatsApp" },
  { to: "/integrations", icon: Webhook, label: "Integrations" },
  { to: "/api-keys", icon: Key, label: "API Keys" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-16 items-center gap-2 border-b border-slate-100 px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white font-bold text-sm">
          V
        </div>
        <span className="text-lg font-bold text-slate-900">VBots</span>
      </div>
      <nav className="flex-1 overflow-y-auto p-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
