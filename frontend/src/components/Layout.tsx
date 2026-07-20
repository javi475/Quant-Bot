import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuthStore } from "../store/authStore";

const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/strategies", label: "Strategies" },
  { to: "/backtesting", label: "Backtesting" },
  { to: "/deployment", label: "Deployment" },
  { to: "/risk", label: "Risk" },
  { to: "/connectors", label: "Connectors" },
  { to: "/settings", label: "Settings" },
];

function linkClasses(isActive: boolean): string {
  return [
    "block rounded px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100",
  ].join(" ");
}

export function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const username = useAuthStore((state) => state.username);
  const logout = useAuthStore((state) => state.logout);

  return (
    <div className="flex min-h-screen bg-slate-950">
      <aside className="flex w-56 flex-shrink-0 flex-col border-r border-slate-800 p-4">
        <div className="mb-6 px-2 text-lg font-bold text-white">ATE-SMP</div>
        <nav className="flex-1 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => linkClasses(isActive)}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <NavLink
          to="/emergency"
          className={({ isActive }) =>
            [
              "block rounded px-3 py-2 text-sm font-bold transition-colors",
              isActive ? "bg-red-700 text-white" : "bg-red-900/40 text-red-300 hover:bg-red-800/60",
            ].join(" ")
          }
        >
          Emergency Controls
        </NavLink>
        <div className="mt-4 border-t border-slate-800 pt-4 text-xs text-slate-500">
          <div className="mb-2 px-2">{username}</div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="w-full rounded px-2 py-1.5 text-left text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
          >
            Log out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-8">{children}</main>
    </div>
  );
}
