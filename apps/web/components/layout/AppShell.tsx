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
  History,
  Menu,
  X,
  ClipboardList,
  Workflow,
} from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { User } from "@supabase/supabase-js";
import { NotificationsDrawer } from "@/components/notifications/NotificationsDrawer";
import { useNotificationsBadge } from "@/lib/hooks/use-notifications";
import { useInboxCount } from "@/lib/hooks/use-inbox";
import { useMe } from "@/lib/hooks/use-me";
import { C } from "@/lib/design-system";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Сегодня",   href: "/today",      icon: <CalendarDays size={18} /> },
  { label: "Воронка",   href: "/pipeline",   icon: <Kanban size={18} /> },
  { label: "База лидов", href: "/leads-pool", icon: <Target size={18} /> },
];

const DISABLED_ITEMS: NavItem[] = [
  { label: "База знаний", href: "#", icon: <BookOpen size={18} />, disabled: true },
  { label: "Команда",   href: "#", icon: <Users size={18} />,    disabled: true },
];

// Shared classes for sidebar nav rows. Keeping the active/inactive
// strings literal (no template interpolation) lets Tailwind's content
// scanner pick them up reliably.
const NAV_BASE = `flex items-center gap-3 px-3 py-2 rounded-full font-medium transition-all duration-200 ${C.bodySm}`;
const NAV_ACTIVE = "bg-brand-soft text-brand-accent-text";
const NAV_INACTIVE = "text-brand-muted";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { data: badge } = useNotificationsBadge();
  const unreadCount = badge?.unread ?? 0;
  const { data: inboxCount } = useInboxCount();
  const inboxPending = inboxCount?.pending ?? 0;
  const { data: me } = useMe();
  const isAdmin = me?.role === "admin";
  const isAdminOrHead = me?.role === "admin" || me?.role === "head";

  useEffect(() => {
    const supabase = getSupabaseBrowserClient();
    supabase.auth.getUser().then(({ data }) => setUser(data.user));

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  // Auto-close the mobile drawer whenever the route changes — otherwise
  // tapping a nav item leaves the drawer covering the page underneath.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

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
  //
  // The `block md:grid` toggle makes the grid (and its 220px column 1
  // reservation) only apply at md+. On narrow viewports the layout
  // collapses to a single column and the sidebar slides in as an
  // overlay — see translate classes on <aside> below.
  return (
    <div
      className="font-sans block md:grid min-h-screen bg-canvas"
      style={{ gridTemplateColumns: "220px minmax(0, 1fr)" }}
    >
      {/* Mobile top bar — only visible on < md */}
      <header className="md:hidden sticky top-0 z-20 bg-white border-b border-brand-border flex items-center justify-between px-4 py-3">
        <Link href="/today" className={`${C.body} font-black tracking-tight ${C.color.text}`}>
          drinkx<span className={C.color.accent}>.</span>crm
        </Link>
        <button
          onClick={() => setMobileNavOpen(true)}
          className="p-2 -mr-2 rounded-full text-brand-muted transition-colors"
          aria-label="Открыть меню"
        >
          <Menu size={20} />
        </button>
      </header>

      {/* Mobile backdrop */}
      {mobileNavOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/30 backdrop-blur-[1px]"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
        />
      )}

      {/* Sidebar.
          Desktop (md+): always visible, fixed at 220px.
          Mobile (<md): slides in from the left when mobileNavOpen flips. */}
      <aside
        className={clsx(
          "fixed top-0 left-0 h-screen w-[220px] bg-white border-r border-brand-border flex flex-col z-40 transition-transform duration-200 ease-out",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Logo + mobile close */}
        <div className="px-5 py-5 border-b border-brand-border flex items-center justify-between">
          <Link
            href="/today"
            className={`${C.body} font-black tracking-tight ${C.color.text} transition-opacity`}
          >
            drinkx<span className={C.color.accent}>.</span>crm
          </Link>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="md:hidden p-1 rounded-full text-brand-muted transition-colors"
            aria-label="Закрыть меню"
          >
            <X size={16} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={item.href as any}
                className={clsx(NAV_BASE, isActive ? NAV_ACTIVE : NAV_INACTIVE)}
              >
                {item.icon}
                {item.label}
              </Link>
            );
          })}

          {/* Inbox — sidebar nav with pending-count badge (Sprint 2.0) */}
          {(() => {
            const href = "/inbox";
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={href as any}
                className={clsx(NAV_BASE, "relative", isActive ? NAV_ACTIVE : NAV_INACTIVE)}
                aria-label={`Входящие${inboxPending > 0 ? ` (${inboxPending} ожидают)` : ""}`}
              >
                <span className="relative">
                  <Inbox size={18} />
                  {inboxPending > 0 && (
                    <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] bg-brand-accent text-white text-[9px] font-mono font-bold rounded-full px-1 flex items-center justify-center tabular-nums">
                      {inboxPending > 99 ? "99+" : inboxPending}
                    </span>
                  )}
                </span>
                Входящие
              </Link>
            );
          })()}

          {/* Admin/head-only: WebForms (Sprint 2.2) */}
          {isAdminOrHead && (() => {
            const href = "/forms";
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={href as any}
                className={clsx(NAV_BASE, isActive ? NAV_ACTIVE : NAV_INACTIVE)}
              >
                <ClipboardList size={18} />
                Формы
              </Link>
            );
          })()}

          {/* Admin/head-only: Automations (Sprint 2.5 G1) */}
          {isAdminOrHead && (() => {
            const href = "/automations";
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={href as any}
                className={clsx(NAV_BASE, isActive ? NAV_ACTIVE : NAV_INACTIVE)}
              >
                <Workflow size={18} />
                Автоматизации
              </Link>
            );
          })()}

          {/* Admin-only: audit journal */}
          {isAdmin && (() => {
            const href = "/audit";
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={href as any}
                className={clsx(NAV_BASE, isActive ? NAV_ACTIVE : NAV_INACTIVE)}
              >
                <History size={18} />
                Журнал
              </Link>
            );
          })()}

          {/* Notifications bell — opens drawer */}
          <button
            onClick={() => setNotifOpen(true)}
            className={clsx(NAV_BASE, "w-full text-left relative", NAV_INACTIVE)}
            aria-label={`Уведомления${unreadCount > 0 ? ` (${unreadCount} непрочитанных)` : ""}`}
          >
            <span className="relative">
              <Bell size={18} />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] bg-brand-accent text-white text-[9px] font-mono font-bold rounded-full px-1 flex items-center justify-center tabular-nums">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </span>
            Уведомления
          </button>

          {/* Settings — Sprint 2.3 G3. All roles see it; mutating
              actions inside (create/edit/delete pipelines) are gated
              to admin/head at the section level via useMe(). */}
          {(() => {
            const href = "/settings";
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                href={href as any}
                className={clsx(NAV_BASE, isActive ? NAV_ACTIVE : NAV_INACTIVE)}
              >
                <Settings size={18} />
                Настройки
              </Link>
            );
          })()}

          {/* Divider */}
          <div className="my-2 border-t border-brand-border" />

          {/* Phase 2 items — disabled */}
          {DISABLED_ITEMS.map((item) => (
            <div
              key={item.label}
              title="Sprint 1.5+"
              className={`${NAV_BASE} text-brand-muted/50 cursor-not-allowed select-none`}
            >
              {item.icon}
              {item.label}
            </div>
          ))}
        </nav>

        {/* User pill */}
        <div className="px-3 py-4 border-t border-brand-border">
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-2xl bg-brand-bg">
            <div className="w-7 h-7 rounded-xl bg-brand-accent flex items-center justify-center shrink-0">
              <span className={`${C.bodyXs} font-bold text-white`}>{avatarLetter}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className={`${C.bodyXs} font-semibold ${C.color.text} truncate`}>{displayName}</p>
              <p className={`text-[10px] font-mono ${C.color.mutedLight} truncate`}>{displayEmail}</p>
            </div>
          </div>
          {user && (
            <button
              onClick={handleSignOut}
              className={`mt-1 w-full text-[10px] font-mono ${C.color.mutedLight} text-center py-1 transition-colors`}
            >
              Выйти
            </button>
          )}
        </div>
      </aside>

      {/* Content area — offset by sidebar width on md+.
          min-w-0 belt-and-suspenders: forces this grid item to honor its
          parent's minmax(0, 1fr) cell instead of its content min-width.
          Pages that need horizontal scroll (Pipeline) handle it with
          their own overflow-x-auto inside. */}
      <div className="md:col-start-2 min-h-screen min-w-0">
        {children}
      </div>

      {/* Notifications drawer */}
      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />
    </div>
  );
}
