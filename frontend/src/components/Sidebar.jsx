import { NavLink } from "react-router-dom"
import { LayoutGrid, Megaphone, Users, FileBarChart2, Plug, Settings, Sparkles } from "lucide-react"

const items = [
  { to: "/", label: "Dashboard", icon: LayoutGrid },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/candidates", label: "Candidates", icon: Users },
  { to: "/reports", label: "Reports", icon: FileBarChart2 },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 bg-navy-900 text-slate-300 flex flex-col h-screen sticky top-0">
      <div className="flex items-center gap-2 px-5 h-16 border-b border-white/10">
        <div className="w-7 h-7 rounded-md bg-brand-500 flex items-center justify-center">
          <Sparkles size={15} className="text-white" />
        </div>
        <span className="text-white font-semibold text-[15px] tracking-tight">Talent Intelligence</span>
      </div>
      <nav className="flex-1 py-4 px-3 space-y-1">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-brand-600 text-white"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
              }`
            }
          >
            <Icon size={17} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-white/10">
        <div className="flex items-center gap-2.5 px-1">
          <div className="w-8 h-8 rounded-full bg-navy-600 flex items-center justify-center text-xs font-semibold text-white">AS</div>
          <div className="leading-tight">
            <p className="text-sm text-white font-medium">Ankush Saxena</p>
            <p className="text-xs text-slate-500">HR Admin</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
