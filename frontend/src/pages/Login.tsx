import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { login, forgotPassword } from "@/lib/api";

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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-slate-100 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-3 mb-2">
            <div className="h-10 w-10 rounded-xl bg-brand-600 flex items-center justify-center text-white font-bold">
              V
            </div>
            <div>
              <CardTitle>VBots</CardTitle>
              <p className="text-sm text-slate-500">AI Voice Calling Platform</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {mode === "login" ? (
            <>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-slate-700">Email</label>
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-slate-700">Password</label>
                  <div className="relative">
                    <Input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                {error && <p className="text-sm text-red-600">{error}</p>}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Signing in..." : "Sign In"}
                </Button>
              </form>
              <button
                type="button"
                onClick={() => {
                  setMode("forgot");
                  setForgotEmail(email);
                  setForgotMsg("");
                }}
                className="mt-3 w-full text-center text-sm text-brand-600 hover:underline"
              >
                Forgot password?
              </button>
            </>
          ) : (
            <>
              <h3 className="mb-1 text-base font-semibold text-slate-800">Reset your password</h3>
              <p className="mb-4 text-sm text-slate-500">
                Enter your email and we'll send you a reset link.
              </p>
              <form onSubmit={handleForgot} className="space-y-4">
                <div>
                  <label className="text-sm font-medium text-slate-700">Email</label>
                  <Input
                    type="email"
                    value={forgotEmail}
                    onChange={(e) => setForgotEmail(e.target.value)}
                    required
                  />
                </div>
                {forgotMsg && <p className="text-sm text-slate-600">{forgotMsg}</p>}
                <Button type="submit" className="w-full" disabled={forgotLoading}>
                  {forgotLoading ? "Sending..." : "Send reset link"}
                </Button>
              </form>
              <button
                type="button"
                onClick={() => setMode("login")}
                className="mt-3 w-full text-center text-sm text-slate-500 hover:underline"
              >
                ← Back to sign in
              </button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
