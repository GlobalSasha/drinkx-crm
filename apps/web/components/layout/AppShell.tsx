"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  CalendarDays,
  Kanban,
  Target,
  Inbox,
  BookOpen,
  Users,
  Settings,
  Bell,
} from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { User } from "@supabase/supabase-js";
import { NotificationsDrawer } from "@/components/notifications/NotificationsDrawer";
import { useNotificationsBadge } from "@/lib/hooks/use-notifications";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Сегодня", href: "/today", icon: <CalendarDays size={18} /> },
  { label: "Pipeline", href: "/pipeline", icon: <Kanban size={18} /> },
  { label: "База лидов", href: "/leads-pool", icon: <Target size={18} /> },
];

const DISABLED_ITEMS: NavItem[] = [
  { label: "Inbox", href: "#", icon: <Inbox size={18} />, disabled: true },
  { label: "Knowledge", href: "#", icon: <BookOpen size={18} />, disabled: true },
  { label: "Team", href: "#", icon: <Users size={18} />, disabled: true },
  { label: "Settings", href: "#", icon: <Settings size={18} />, disabled: true },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const { data: badge } = useNotificationsBadge();
  const unreadCount = badge?.unread ?? 0;

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => setUser(data.user));

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function handleSignOut() {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
    router.push("/sign-in");
  }

  const displayName =
    (user?.user_metadata?.full_name as string | undefined) ??
    user?.email?.split("@")[0] ??
    "…";
  const displayEmail = user?.email ?? "";
  const avatarLetter = displayName[0]?.toUpperCase() ?? "?";

  // gridTemplateColumns uses minmax(0, 1fr) so the content cell can't
  // grow past the available viewport width — without that clamp, default
  // min-width: auto on grid items lets wide content (e.g., 12-column
  // Kanban board on /pipeline) push the cell wider than the viewport
  // and the browser horizontal-scrolls the whole page, taking the header
  // off-screen.
  return (
    <div className="grid min-h-screen bg-canvas" style={{ gridTemplateColumns: "220px minmax(0, 1fr)" }}>
      {/* Sidebar */}
      <aside className="fixed top-0 left-0 h-screen w-[220px] bg-white border-r border-black/5 flex flex-col z-20">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-black/5">
          <span className="text-lg font-extrabold tracking-tight">
            drinkx<span className="text-accent">.</span>crm
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={item.href as any}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200",
                  isActive
                    ? "bg-accent/10 text-accent"
                    : "text-muted hover:bg-black/5"
                )}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}

          {/* Notifications bell — opens drawer */}
          <button
            onClick={() => setNotifOpen(true)}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 w-full text-left relative",
              "text-muted hover:bg-black/5",
            )}
            aria-label={`Уведомления${unreadCount > 0 ? ` (${unreadCount} непрочитанных)` : ""}`}
          >
            <span className="relative">
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] bg-accent text-white text-[9px] font-mono font-bold rounded-pill px-1 flex items-center justify-center tabular-nums">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </span>
            Уведомления
          </button>

          {/* Divider */}
          <div className="my-2 border-t border-black/5" />

          {/* Phase 2 items — disabled */}
          {DISABLED_ITEMS.map((item) => (
            <div
              key={item.label}
              title="Sprint 1.5+"
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold text-muted-3 cursor-not-allowed select-none"
            >
              {item.icon}
              {item.label}
            </div>
          ))}
        </nav>

        {/* User pill */}
        <div className="px-3 py-4 border-t border-black/5">
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-canvas">
            <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
              <span className="text-[11px] font-bold text-accent">{avatarLetter}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-ink truncate">{displayName}</p>
              <p className="text-[10px] font-mono text-muted-3 truncate">{displayEmail}</p>
            </div>
          </div>
          {user && (
            <button
              onClick={handleSignOut}
              className="mt-1 w-full text-[10px] font-mono text-muted-3 hover:text-accent text-center py-1 transition-colors"
            >
              Выйти
            </button>
          )}
        </div>
      </aside>

      {/* Content area — offset by sidebar width.
          min-w-0 belt-and-suspenders: forces this grid item to honor its
          parent's minmax(0, 1fr) cell instead of its content min-width.
          Pages that need horizontal scroll (Pipeline) handle it with
          their own overflow-x-auto inside. */}
      <div className="col-start-2 min-h-screen min-w-0">
        {children}
      </div>

      {/* Notifications drawer */}
      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />
    </div>
  );
}
