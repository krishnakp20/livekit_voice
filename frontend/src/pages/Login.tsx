import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Eye,
  EyeOff,
  Languages,
  Loader2,
  Lock,
  Mail,
  PhoneCall,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { login, forgotPassword } from "@/lib/api";

const WAVE_BARS = [30, 55, 80, 45, 95, 60, 35, 70, 50, 85, 40, 65, 30, 75];

const FEATURES = [
  {
    icon: PhoneCall,
    title: "Inbound & outbound AI calling",
    text: "Voice agents that answer, dial and follow up around the clock.",
  },
  {
    icon: Languages,
    title: "Hindi, English & Hinglish",
    text: "Natural conversations in the language your customer prefers.",
  },
  {
    icon: Activity,
    title: "Live insight on every call",
    text: "Transcripts, per-turn latency, sentiment and CRM hand-off.",
  },
];

function Logo({ className = "" }: { className?: string }) {
  return (
    <img
      src="/dialdesk-logo.png"
      alt="DialDesk"
      width={150}
      height={50}
      className={`h-[50px] w-[150px] select-none object-contain ${className}`}
      draggable={false}
    />
  );
}

export default function Login() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Forgot-password state
  const [mode, setMode] = useState<"login" | "forgot">("login");
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotMsg, setForgotMsg] = useState("");
  const [forgotLoading, setForgotLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await login(email, password);
      localStorage.setItem("access_token", data.access_token);
      await refreshUser();
      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e: FormEvent) => {
    e.preventDefault();
    setForgotLoading(true);
    setForgotMsg("");
    try {
      await forgotPassword(forgotEmail);
      setForgotMsg("If that email is registered, a reset link has been sent. Check your inbox.");
    } catch {
      setForgotMsg("Something went wrong. Please try again.");
    } finally {
      setForgotLoading(false);
    }
  };

  return (
    <div className="grid min-h-screen bg-white lg:h-screen lg:grid-cols-[1.05fr_1fr] lg:overflow-hidden">
      {/* ── Brand panel (desktop) ───────────────────────────────────────── */}
      <aside className="relative hidden min-h-0 overflow-hidden bg-gradient-to-br from-brand-700 via-brand-800 to-slate-900 p-[clamp(20px,4.5vh,48px)] text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-100"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.05) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse at 30% 40%, black 30%, transparent 75%)",
            WebkitMaskImage: "radial-gradient(ellipse at 30% 40%, black 30%, transparent 75%)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-400/30 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-indigo-500/25 blur-3xl"
        />

        <div className="relative">
          <div className="inline-flex rounded-2xl bg-white px-4 py-[clamp(4px,1.2vh,10px)] shadow-lg shadow-black/20">
            <Logo />
          </div>
        </div>

        <div className="relative max-w-lg">
          <div className="mb-6 flex h-12 items-end gap-1.5 [@media(max-height:800px)]:hidden" aria-hidden>
            {WAVE_BARS.map((h, i) => (
              <span
                key={i}
                className="w-1.5 rounded-full bg-white/70 motion-safe:animate-pulse"
                style={{
                  height: `${h}%`,
                  opacity: 0.35 + (h / 100) * 0.65,
                  animationDelay: `${i * 120}ms`,
                  animationDuration: "1.8s",
                }}
              />
            ))}
          </div>
          <h1 className="text-[clamp(1.5rem,4.6vh,2.25rem)] font-semibold leading-tight tracking-tight text-white">
            Voice AI that talks to your customers, like your best agent.
          </h1>
          <p className="mt-[clamp(6px,1.4vh,12px)] text-[clamp(0.8rem,1.9vh,1rem)] leading-relaxed text-brand-100/90">
            Build, launch and monitor AI voice agents from one dashboard.
          </p>

          <ul className="mt-[clamp(14px,3.2vh,32px)] space-y-[clamp(8px,1.9vh,16px)] [@media(max-height:430px)]:hidden">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex items-start gap-3.5">
                <span className="flex h-[clamp(30px,4.8vh,40px)] w-[clamp(30px,4.8vh,40px)] shrink-0 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15 backdrop-blur">
                  <Icon className="h-[clamp(16px,2.4vh,20px)] w-[clamp(16px,2.4vh,20px)] text-brand-100" />
                </span>
                <span>
                  <span className="block text-sm font-semibold leading-snug text-white">{title}</span>
                  <span className="block text-[clamp(0.75rem,1.7vh,0.875rem)] leading-snug text-brand-100/80">
                    {text}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-brand-100/60">
          © {new Date().getFullYear()} DialDesk. All rights reserved.
        </p>
      </aside>

      {/* ── Form panel ──────────────────────────────────────────────────── */}
      <main className="flex min-h-0 items-center justify-center bg-gradient-to-b from-white to-slate-50 px-6 py-8 sm:px-10 lg:overflow-y-auto">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <Logo />
          </div>

          {mode === "login" ? (
            <>
              <div className="mb-8">
                <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Welcome back</h2>
                <p className="mt-1.5 text-sm text-slate-500">Sign in to your dashboard.</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      autoFocus
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="h-11 rounded-xl pl-10"
                    />
                  </div>
                </div>

                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                      Password
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        setMode("forgot");
                        setForgotEmail(email);
                        setForgotMsg("");
                      }}
                      className="text-sm font-medium text-brand-600 hover:text-brand-700 hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      placeholder="Enter your password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="h-11 rounded-xl pl-10 pr-11"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      className="absolute inset-y-0 right-0 flex items-center rounded-r-xl px-3.5 text-slate-400 transition-colors hover:text-slate-600"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {error && (
                  <div
                    role="alert"
                    className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                  >
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    {error}
                  </div>
                )}

                <Button
                  type="submit"
                  size="lg"
                  className="h-11 w-full rounded-xl text-sm shadow-md shadow-brand-600/25"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Signing in...
                    </>
                  ) : (
                    "Sign In"
                  )}
                </Button>
              </form>
            </>
          ) : (
            <>
              <div className="mb-8">
                <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
                  Reset your password
                </h2>
                <p className="mt-1.5 text-sm text-slate-500">
                  Enter your email and we'll send you a reset link.
                </p>
              </div>

              <form onSubmit={handleForgot} className="space-y-5">
                <div>
                  <label
                    htmlFor="forgot-email"
                    className="mb-1.5 block text-sm font-medium text-slate-700"
                  >
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <Input
                      id="forgot-email"
                      type="email"
                      autoComplete="email"
                      autoFocus
                      placeholder="you@company.com"
                      value={forgotEmail}
                      onChange={(e) => setForgotEmail(e.target.value)}
                      required
                      className="h-11 rounded-xl pl-10"
                    />
                  </div>
                </div>

                {forgotMsg && (
                  <p
                    role="status"
                    className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-600"
                  >
                    {forgotMsg}
                  </p>
                )}

                <Button
                  type="submit"
                  size="lg"
                  className="h-11 w-full rounded-xl text-sm shadow-md shadow-brand-600/25"
                  disabled={forgotLoading}
                >
                  {forgotLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    "Send reset link"
                  )}
                </Button>
              </form>

              <button
                type="button"
                onClick={() => setMode("login")}
                className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 transition-colors hover:text-slate-800"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to sign in
              </button>
            </>
          )}

          <p className="mt-10 text-center text-xs text-slate-400 lg:hidden">
            © {new Date().getFullYear()} DialDesk. All rights reserved.
          </p>
        </div>
      </main>
    </div>
  );
}
