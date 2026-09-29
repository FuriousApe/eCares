import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { makeApi, type Api } from "./api";
import type { Meta, Role } from "./types";

export interface DemoUser {
  id: string;
  name: string;
  role: Role;
}

// No real auth in the MVP: the API trusts X-User-Role / X-User-Id, so signing
// in is just picking who you are.
export const USERS: DemoUser[] = [
  { id: "sched1", name: "Jordan Lee", role: "scheduler" },
  { id: "clin1", name: "Dr. Patel", role: "clinical" },
  { id: "admin1", name: "Sam Rivera", role: "admin" },
];

const STORAGE_KEY = "caregap.user";

function loadUser(): DemoUser {
  try {
    const id = localStorage.getItem(STORAGE_KEY);
    return USERS.find((u) => u.id === id) ?? USERS[0];
  } catch {
    return USERS[0];
  }
}

interface Session {
  user: DemoUser;
  setUser: (u: DemoUser) => void;
  api: Api;
  meta: Meta | null;
  metaError: string | null;
  refreshMeta: () => void;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<DemoUser>(loadUser);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const api = useMemo(() => makeApi({ role: user.role, userId: user.id }), [user]);

  const refreshMeta = useCallback(() => {
    api.meta().then(
      (m) => { setMeta(m); setMetaError(null); },
      (e: Error) => setMetaError(e.message),
    );
  }, [api]);

  useEffect(refreshMeta, [refreshMeta]);

  const setUser = useCallback((u: DemoUser) => {
    try { localStorage.setItem(STORAGE_KEY, u.id); } catch { /* storage blocked */ }
    setUserState(u);
  }, []);

  const value = useMemo(
    () => ({ user, setUser, api, meta, metaError, refreshMeta }),
    [user, setUser, api, meta, metaError, refreshMeta],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside SessionProvider");
  return s;
}
