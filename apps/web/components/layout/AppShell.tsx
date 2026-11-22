"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { clsx } from "clsx";
import { Bell, CheckSquare, Home, Menu, Users, X } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { User } from "@supabase/supabase-js";
import { NotificationsDrawer } from "@/components/notifications/NotificationsDrawer";
import {
  GlobalSearch,
  useGlobalSearchHotkey,
} from "@/components/search/GlobalSearch";
import { C } from "@/lib/design-system";
import { SidebarNavContainer } from "./SidebarNavContainer";
import { DrinkXLogo } from "./DrinkXLogo";
import { TaskReminders } from "@/components/reminders/TaskReminders";
import { useNotificationsBadge } from "@/lib/hooks/use-notifications";
import { useUnreadTitle } from "@/lib/title-badge";
import { useDesktopNotifications } from "@/lib/desktop-notifications";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  useGlobalSearchHotkey(() => setSearchOpen(true));
  const { data: badge } = useNotificationsBadge();
  useUnreadTitle(badge?.unread ?? 0);
  useDesktopNotifications();

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

  // Stable ref so SidebarNavContainer's items useMemo doesn't rebuild
  // on every AppShell render.
  const openNotifications = useCallback(() => setNotifOpen(true), []);
  // The lead card has its own bottom action bar — two bars would stack.
  const showTabBar = !pathname.startsWith("/leads/");
  const openSearch = useCallback(() => setSearchOpen(true), []);

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
      className="font-sans block md:grid min-h-screen bg-brand-bg"
      style={{ gridTemplateColumns: "220px minmax(0, 1fr)" }}
    >
      {/* Mobile top bar — only visible on < md */}
      <header className="md:hidden sticky top-0 z-20 bg-white border-b border-brand-border flex items-center justify-between px-4 py-3">
        <Link href="/today" aria-label="DrinkX — на главную" className={`rounded-full ${C.color.text} ${C.focusRing}`}>
          <DrinkXLogo className="h-6 w-auto" />
        </Link>
        <div className="flex items-center gap-1 -mr-2.5">
          <MobileBell onClick={openNotifications} />
          <button
            onClick={() => setMobileNavOpen(true)}
            className="p-2.5 rounded-full text-brand-muted transition-colors"
            aria-label="Открыть меню"
          >
            <Menu size={22} />
          </button>
        </div>
      </header>

      {/* Mobile backdrop */}
      {mobileNavOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/30"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden
        />
      )}

      {/* Sidebar.
          Desktop (md+): always visible, fixed at 220px.
          Mobile (<md): slides in from the left when mobileNavOpen flips. */}
      <aside
        style={{
          backgroundColor: "var(--sidebar-bg)",
          color: "var(--sidebar-fg)",
          borderRight: "1px solid var(--sidebar-border)",
        }}
        className={clsx(
          "fixed top-0 left-0 h-screen w-sidebar flex flex-col z-40 transition-transform duration-200 ease-out",
          mobileNavOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Logo + mobile close.
            Inside the sidebar, text colors inherit from --sidebar-fg
            (set on <aside> above) so the dark presets (graphite/coffee)
            stay legible. We deliberately do NOT pin `text-brand-primary`
            here — that would force #111111 on top of a dark surface. */}
        <div
          style={{ borderBottom: "1px solid var(--sidebar-border)" }}
          className="px-5 py-5 flex items-center justify-between"
        >
          <Link
            href="/today"
            aria-label="DrinkX — на главную"
            className={`rounded-full transition-opacity hover:opacity-80 ${C.focusRing}`}
          >
            <DrinkXLogo className="h-6 w-auto" />
          </Link>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="md:hidden p-2.5 -m-2 rounded-full opacity-70 hover:opacity-100 transition-opacity"
            aria-label="Закрыть меню"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav + sliding pill. Polling, hover state, and pill measurement
            all live in their own components so they don't re-render the
            rest of the shell. */}
        <SidebarNavContainer onNotificationsClick={openNotifications} onSearchClick={openSearch} />

        {/* User pill — links to /settings/profile */}
        <div
          style={{ borderTop: "1px solid var(--sidebar-border)" }}
          className="px-3 py-4"
        >
          <Link
            href="/settings/profile"
            style={{ backgroundColor: "var(--sidebar-hover)" }}
            className="flex items-center gap-2.5 px-3 py-2.5 rounded-card hover:opacity-90 transition-opacity"
          >
            <div className="w-7 h-7 rounded-xl bg-brand-accent flex items-center justify-center shrink-0">
              <span className="type-caption font-semibold text-white">{avatarLetter}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="type-label truncate">{displayName}</p>
              <p className="text-xs font-mono opacity-60 truncate">{displayEmail}</p>
            </div>
          </Link>
          {user && (
            <button
              onClick={handleSignOut}
              className="mt-1 w-full text-xs font-mono opacity-60 hover:opacity-100 text-center py-1 transition-opacity"
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
      <main
        id="main-content"
        className={clsx(
          "md:col-start-2 min-h-screen min-w-0",
          showTabBar && "pb-24 md:pb-0",
        )}
      >
        {children}
      </main>

      {showTabBar && (
        <MobileTabBar pathname={pathname} onMore={() => setMobileNavOpen(true)} />
      )}

      {/* Notifications drawer */}
      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />

      {/* Global search — Cmd+K */}
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />

      {/* In-app task-due reminders (glass toasts, bottom-right) */}
      <TaskReminders />
    </div>
  );
}

const TABS = [
  { href: "/today", label: "Сегодня", icon: Home },
  { href: "/pipeline", label: "Лиды", icon: Users },
  { href: "/tasks", label: "Задачи", icon: CheckSquare },
] as const;

// Нижнее меню телефона: три главных раздела под большим пальцем, остальное —
// в «Ещё» (то же боковое меню, что открывает кнопка в шапке).
function MobileTabBar({ pathname, onMore }: { pathname: string; onMore: () => void }) {
  const item =
    "flex-1 min-h-11 flex flex-col items-center justify-center gap-1 rounded-lg type-label transition-colors";
  return (
    <nav
      aria-label="Главное меню"
      className="md:hidden fixed inset-x-0 bottom-0 z-30 bg-white border-t border-brand-border px-2 pt-2"
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
    >
      <div className="flex items-stretch gap-1">
        {TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={clsx(item, active ? "text-brand-accent-text" : "text-brand-muted")}
            >
              <Icon size={20} aria-hidden />
              {label}
            </Link>
          );
        })}
        <button type="button" onClick={onMore} className={clsx(item, "text-brand-muted")}>
          <Menu size={20} aria-hidden />
          Ещё
        </button>
      </div>
    </nav>
  );
}

// На телефоне меню спрятано, поэтому колокольчик с числом непрочитанных
// вынесен в верхнюю панель: иначе вопросы и задачи от руководителя не видны.
function MobileBell({ onClick }: { onClick: () => void }) {
  const { data } = useNotificationsBadge();
  const unread = data?.unread ?? 0;
  return (
    <button
      type="button"
      onClick={onClick}
      className="relative p-2.5 rounded-full text-brand-muted transition-colors"
      aria-label={`Уведомления${unread > 0 ? ` (${unread} непрочитанных)` : ""}`}
    >
      <Bell size={22} />
      {unread > 0 && (
        <span className="absolute top-1 right-1 min-w-4 h-4 bg-brand-accent text-white text-xs font-mono font-medium rounded-full px-1 flex items-center justify-center tabular-nums">
          {unread > 999 ? "999+" : unread}
        </span>
      )}
    </button>
  );
}
