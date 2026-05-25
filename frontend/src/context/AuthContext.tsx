import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { getMe } from "@/lib/api";

interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  client_id: number | null;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setUser(null);
      return;
    }
    const res = await getMe();
    setUser(res.data);
  }, []);

  useEffect(() => {
    refreshUser()
      .catch(() => {
        localStorage.removeItem("access_token");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [refreshUser]);

  return (
    <AuthContext.Provider value={{ user, loading, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
