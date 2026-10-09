import { NavLink, useNavigate } from "react-router-dom";
import { MessageSquareText, LayoutDashboard, LogOut, Users, UserRound, BrainCircuit, BellRing, Scale, SlidersHorizontal, ScrollText } from "lucide-react";
import { clsx } from "clsx";
import { useAuth } from "../lib/auth";
import { Avatar } from "./Avatar";
import logo from "../assets/gets-logo.png";

export function Sidebar() {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  const links = [
    { to: "/chat", label: "Assistant", icon: MessageSquareText },
    { to: "/dashboard", label: "Dashboards", icon: LayoutDashboard },
    { to: "/predictions", label: "Predictions", icon: BrainCircuit },
    { to: "/alerts", label: "Alerts", icon: BellRing },
    { to: "/recommend", label: "Recommend", icon: Scale },
    { to: "/optimize", label: "Optimize", icon: SlidersHorizontal },
    ...(user?.role === "admin"
      ? [{ to: "/team", label: "Team", icon: Users },
         { to: "/audit", label: "Audit", icon: ScrollText }]
      : []),
  ];

  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col bg-navy-900 text-white">
      <div className="flex items-center gap-3 px-5 pt-6 pb-5">
        <img src={logo} alt="GETS" className="size-10 rounded-full bg-white p-0.5" />
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
        {user && (
          <NavLink
            to="/profile"
            className={({ isActive }) =>
              clsx(
                "mb-1 flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors",
                isActive ? "bg-white/12" : "hover:bg-white/8",
              )
            }
          >
            <Avatar user={user} size={30} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-white">
                {user.first_name} {user.last_name}
              </div>
              <div className="truncate text-[11px] text-white/50">{user.job_title}</div>
            </div>
            <UserRound className="ml-auto size-4 text-white/40" />
          </NavLink>
        )}
        <button
          onClick={() => { logout(); nav("/login"); }}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm text-white/65 transition-colors hover:bg-white/8 hover:text-white"
        >
          <LogOut className="size-4.5" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
