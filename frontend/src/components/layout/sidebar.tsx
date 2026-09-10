import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";
import { NAV_GROUPS } from "./nav";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div className="px-2 text-lg font-bold tracking-tight">Hexagare</div>
      <div className="flex flex-col gap-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <div className="flex items-center gap-2 px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <group.icon className="size-3.5" />
              {group.label}
            </div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                    isActive && "bg-accent font-medium text-accent-foreground",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </div>
    </nav>
  );
}
