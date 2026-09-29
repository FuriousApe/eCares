import { useEffect } from "react";
import { PanelProvider } from "./components/PatientPanel";
import { ErrorState, ToastProvider } from "./components/ui";
import { fmtDate, ROLE_LABEL } from "./format";
import { useHashRoute } from "./hooks";
import { Admin } from "./pages/Admin";
import { Patients } from "./pages/Patients";
import { Worklist } from "./pages/Worklist";
import { API_BASE } from "./api";
import { SessionProvider, USERS, useSession } from "./session";

const NAV = [
  { to: "/worklist", label: "Worklist", roles: ["scheduler", "clinical", "admin"] },
  { to: "/patients", label: "Patients", roles: ["scheduler", "clinical", "admin"] },
  { to: "/admin", label: "Admin", roles: ["admin"] },
];

function Shell() {
  const { user, setUser, meta, metaError, refreshMeta } = useSession();
  const [route, go] = useHashRoute();
  const items = NAV.filter((n) => n.roles.includes(user.role));
  const page = items.find((n) => route.startsWith(n.to)) ?? items[0];

  // "/" jumps to the search box from anywhere, like most call-center tools.
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) {
        e.preventDefault();
        document.getElementById("search")?.focus();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <div className="topbar-in">
          <div className="brand"><span className="brand-mark" aria-hidden>+</span> CareGap</div>
          <nav aria-label="Main">
            {items.map((n) => (
              <a key={n.to} href={`#${n.to}`} className={page.to === n.to ? "nav nav-on" : "nav"}
                aria-current={page.to === n.to ? "page" : undefined}>{n.label}</a>
            ))}
          </nav>
          <div className="topbar-right">
            {meta && <span className="asof" title="The date the system is working as of">As of {fmtDate(meta.as_of_date)}</span>}
            <label className="who">
              <span className="avatar" aria-hidden>{user.name.replace("Dr. ", "").charAt(0)}</span>
              <span className="visually-hidden">Signed in as</span>
              <select value={user.id} onChange={(e) => {
                const u = USERS.find((x) => x.id === e.target.value)!;
                setUser(u);
                if (u.role !== "admin" && route.startsWith("/admin")) go("/worklist");
              }}>
                {USERS.map((u) => <option key={u.id} value={u.id}>{u.name} · {ROLE_LABEL[u.role]}</option>)}
              </select>
            </label>
          </div>
        </div>
      </header>

      <main id="main" className="page">
        {metaError ? (
          <ErrorState message={`${metaError} Is the API running at ${API_BASE}?`} onRetry={refreshMeta} />
        ) : (
          // Keyed by user so switching person always starts from a clean list.
          <div key={user.id}>
            {page.to === "/worklist" && <Worklist />}
            {page.to === "/patients" && <Patients />}
            {page.to === "/admin" && <Admin />}
          </div>
        )}
      </main>
    </>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <ToastProvider>
        <PanelProvider>
          <Shell />
        </PanelProvider>
      </ToastProvider>
    </SessionProvider>
  );
}
