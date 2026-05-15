"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { clsx } from "clsx";
import { Menu, X } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { User } from "@supabase/supabase-js";
import { NotificationsDrawer } from "@/components/notifications/NotificationsDrawer";
import {
  GlobalSearch,
  useGlobalSearchHotkey,
} from "@/components/search/GlobalSearch";
import { C } from "@/lib/design-system";
import { SidebarNavContainer } from "./SidebarNavContainer";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  useGlobalSearchHotkey(() => setSearchOpen(true));

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
        <Link href="/today" className={`type-body font-bold tracking-tight ${C.color.text}`}>
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
        style={{
          backgroundColor: "var(--sidebar-bg)",
          color: "var(--sidebar-fg)",
          borderRight: "1px solid var(--sidebar-border)",
        }}
        className={clsx(
          "fixed top-0 left-0 h-screen w-[220px] flex flex-col z-40 transition-transform duration-200 ease-out",
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
            className="type-body font-bold tracking-tight transition-opacity"
          >
            drinkx<span className={C.color.accent}>.</span>crm
          </Link>
          <button
            onClick={() => setMobileNavOpen(false)}
            className="md:hidden p-1 rounded-full opacity-70 hover:opacity-100 transition-opacity"
            aria-label="Закрыть меню"
          >
            <X size={16} />
          </button>
        </div>

        {/* Nav + sliding pill. Polling, hover state, and pill measurement
            all live in their own components so they don't re-render the
            rest of the shell. */}
        <SidebarNavContainer onNotificationsClick={openNotifications} />

        {/* User pill — links to /settings/profile */}
        <div
          style={{ borderTop: "1px solid var(--sidebar-border)" }}
          className="px-3 py-4"
        >
          <Link
            href="/settings/profile"
            style={{ backgroundColor: "var(--sidebar-hover)" }}
            className="flex items-center gap-2.5 px-3 py-2.5 rounded-2xl hover:opacity-90 transition-opacity"
          >
            <div className="w-7 h-7 rounded-xl bg-brand-accent flex items-center justify-center shrink-0">
              <span className="type-caption font-bold text-white">{avatarLetter}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="type-caption font-semibold truncate">{displayName}</p>
              <p className="text-[10px] font-mono opacity-60 truncate">{displayEmail}</p>
            </div>
          </Link>
          {user && (
            <button
              onClick={handleSignOut}
              className="mt-1 w-full text-[10px] font-mono opacity-60 hover:opacity-100 text-center py-1 transition-opacity"
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
      <main id="main-content" className="md:col-start-2 min-h-screen min-w-0">
        {children}
      </main>

      {/* Notifications drawer */}
      <NotificationsDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />

      {/* Global search — Cmd+K */}
      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
