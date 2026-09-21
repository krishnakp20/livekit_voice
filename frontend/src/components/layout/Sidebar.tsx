import { cn } from "@/lib/utils";
import {
  BarChart3,
  Bot,
  Building2,
  CreditCard,
  FileText,
  GitBranch,
  Hash,
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
import { useAuth } from "@/context/AuthContext";

type Item = { to: string; icon: typeof LayoutDashboard; label: string; end?: boolean };
type Group = { heading: string; items: Item[] };

const groups: Group[] = [
  {
    heading: "Operations",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
      { to: "/live-calls", icon: PhoneCall, label: "Live Calls" },
      { to: "/campaigns", icon: Target, label: "Campaigns" },
      { to: "/leads", icon: Users, label: "Leads" },
      { to: "/calls", icon: Phone, label: "Call History" },
    ],
  },
  {
    heading: "AI Management",
    items: [
      { to: "/agents", icon: Bot, label: "AI Agents" },
      { to: "/dispatch", icon: GitBranch, label: "Dispatch Rules" },
    ],
  },
  {
    heading: "Telephony",
    items: [
      { to: "/sip-trunks", icon: Radio, label: "SIP Trunks" },
      { to: "/phone-numbers", icon: Hash, label: "Phone Numbers" },
    ],
  },
  {
    heading: "Analytics",
    items: [
      { to: "/reports", icon: FileText, label: "Reports" },
      { to: "/analytics", icon: BarChart3, label: "Analytics" },
    ],
  },
  {
    heading: "Integrations",
    items: [
      { to: "/whatsapp", icon: MessageSquare, label: "WhatsApp" },
      { to: "/integrations", icon: Webhook, label: "Integrations" },
      { to: "/api-keys", icon: Key, label: "API Keys" },
    ],
  },
  {
    heading: "Admin",
    items: [
      { to: "/billing", icon: CreditCard, label: "Billing" },
      { to: "/settings", icon: Settings, label: "Settings" },
    ],
  },
];

export function Sidebar() {
  const { user } = useAuth();

  // Super admin gets a Clients entry at the very top.
  const renderGroups: Group[] =
    user?.role === "super_admin"
      ? [{ heading: "Platform", items: [{ to: "/clients", icon: Building2, label: "Clients" }] }, ...groups]
      : groups;

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-60 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-16 shrink-0 items-center border-b border-slate-100 px-5">
        <img
          src="/dialdesk-logo.png"
          alt="DialDesk"
          width={150}
          height={50}
          className="h-[50px] w-[150px] select-none object-contain"
          draggable={false}
        />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {renderGroups.map((group) => (
          <div key={group.heading} className="mb-5">
            <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              {group.heading}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
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
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
