import { cn } from "@/lib/utils";

const colors: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  inactive: "bg-slate-100 text-slate-600",
  running: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  draft: "bg-yellow-100 text-yellow-800",
  ringing: "bg-amber-100 text-amber-800",
};

export function Badge({ status, className }: { status: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        colors[status] || "bg-slate-100 text-slate-600",
        className
      )}
    >
      {status}
    </span>
  );
}
