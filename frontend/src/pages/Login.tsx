import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { login } from "@/lib/api";

export default function Login() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState("admin@demo.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700">Email</label>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Password</label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in..." : "Sign In"}
            </Button>
          </form>
          <p className="mt-4 text-xs text-slate-400 text-center">
            Demo: admin@demo.com / admin123
          </p>
          <p className="mt-2 text-xs text-amber-600 text-center">
            Always open the app at <strong>http://localhost:5173</strong> (not 127.0.0.1) so login token is stored correctly.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
