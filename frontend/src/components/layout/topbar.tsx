import { LogOut, Menu, User as UserIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCurrentUser, useLogout } from "@/hooks/use-auth";

function initials(email: string, first: string, last: string) {
  if (first || last) return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
  return email.slice(0, 2).toUpperCase();
}

export function Topbar({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const user = useCurrentUser();
  const logout = useLogout();

  return (
    <header className="flex h-14 items-center gap-3 border-b bg-background px-4">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
      >
        <Menu />
      </Button>
      <div className="flex-1" />
      {user && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2 px-2">
              <span className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
                {initials(user.email, user.first_name, user.last_name)}
              </span>
              <span className="hidden text-sm sm:inline">{user.email}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="font-medium">
                {user.first_name || user.last_name
                  ? `${user.first_name} ${user.last_name}`.trim()
                  : user.email}
              </div>
              <div className="text-xs font-normal text-muted-foreground">
                {user.roles.length ? user.roles.join(", ") : "No role"}
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>
              <UserIcon />
              Profile (coming soon)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => logout.mutate()} disabled={logout.isPending}>
              <LogOut />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </header>
  );
}
