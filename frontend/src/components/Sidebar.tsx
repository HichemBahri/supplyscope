import { NavLink, useNavigate } from "react-router-dom";
import { MessageSquareText, LayoutDashboard, LogOut, Factory } from "lucide-react";
import { clsx } from "clsx";
import { useAuth } from "../lib/auth";

const links = [
  { to: "/chat", label: "Assistant", icon: MessageSquareText },
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
];

export function Sidebar() {
  const { logout } = useAuth();
  const nav = useNavigate();
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col bg-navy-900 text-white">
      <div className="flex items-center gap-3 px-5 pt-6 pb-5">
        <div className="grid size-9 place-items-center rounded-md bg-white/10">
          <Factory className="size-5" />
        </div>
        <div>
          <div className="font-display text-lg font-bold leading-tight">SupplyScope</div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-white/50">GETS · Sfax</div>
        </div>
      </div>
      <nav className="mt-2 flex flex-col gap-1 px-3">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium",
                "transition-colors duration-150",
                isActive ? "bg-white/12 text-white" : "text-white/65 hover:bg-white/8 hover:text-white",
              )
            }
          >
            <Icon className="size-4.5" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto px-3 pb-5">
        <button
          onClick={() => { logout(); nav("/login"); }}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-white/65 transition-colors hover:bg-white/8 hover:text-white"
        >
          <LogOut className="size-4.5" />
          Se déconnecter
        </button>
      </div>
    </aside>
  );
}
