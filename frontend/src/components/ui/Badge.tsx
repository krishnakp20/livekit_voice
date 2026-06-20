import { cn } from "@/lib/utils";

type Tone = "success" | "warning" | "error" | "info" | "neutral";

const TONE: Record<Tone, { badge: string; dot: string }> = {
  success: { badge: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", dot: "bg-emerald-500" },
  warning: { badge: "bg-amber-50 text-amber-700 ring-amber-600/20", dot: "bg-amber-500" },
  error: { badge: "bg-red-50 text-red-700 ring-red-600/20", dot: "bg-red-500" },
  info: { badge: "bg-brand-50 text-brand-700 ring-brand-600/20", dot: "bg-brand-600" },
  neutral: { badge: "bg-slate-100 text-slate-600 ring-slate-500/20", dot: "bg-slate-400" },
};

// Map every known status → a semantic tone.
const STATUS_TONE: Record<string, Tone> = {
  // calls
  active: "success",
  completed: "success",
  ringing: "warning",
  transferred: "info",
  failed: "error",
  missed: "error",
  // leads
  new: "neutral",
  dialing: "warning",
  connected: "success",
  no_answer: "warning",
  // campaigns
  running: "info",
  paused: "warning",
  draft: "neutral",
  stopped: "neutral",
  // generic
  inactive: "neutral",
  pending: "warning",
};

export function Badge({
  status,
  tone,
  dot = true,
  className,
}: {
  status: string;
  tone?: Tone;
  dot?: boolean;
  className?: string;
}) {
  const resolved = tone || STATUS_TONE[status?.toLowerCase()] || "neutral";
  const c = TONE[resolved];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-inset",
        c.badge,
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", c.dot)} />}
      {status?.replace(/_/g, " ")}
    </span>
  );
}
