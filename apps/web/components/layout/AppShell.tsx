"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  id: string;
  label: string;
  icon: React.ReactNode;
  href?: string;
  badge?: number;
  ariaLabel?: string;
  onClick?: () => void;
}

interface DisabledNavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const DISABLED_ITEMS: DisabledNavItem[] = [
  { id: "knowledge", label: "База знаний", icon: <BookOpen size={18} /> },
  { id: "team",      label: "Команда",     icon: <Users size={18} /> },
];

// Shared row geometry. The pill animates over these — keep paddings and
// gaps consistent across all rows so the pill height stays stable.
const NAV_ROW = `relative z-10 flex items-center gap-3 px-3 py-2 rounded-full font-medium transition-colors duration-200 ${C.bodySm}`;

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

  // ─── Sliding-pill state ───────────────────────────────────
  // The pill is a single absolutely-positioned element inside <nav>.
  // It translates to whichever item is currently "highlighted":
  // hovered if the cursor is over an item, otherwise the active route.
  const navRef = useRef<HTMLElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [pill, setPill] = useState<{
    top: number;
    height: number;
    visible: boolean;
  }>({ top: 0, height: 0, visible: false });

  // Items list. Order matches what the sidebar renders top-to-bottom;
  // gating by role happens at build time so the active-route lookup
  // can't accidentally match a hidden row.
  const items: NavItem[] = useMemo(() => {
    const base: NavItem[] = [
      { id: "today",      label: "Сегодня",   href: "/today",      icon: <CalendarDays size={18} /> },
      { id: "pipeline",   label: "Воронка",   href: "/pipeline",   icon: <Kanban size={18} /> },
      { id: "leads-pool", label: "База лидов", href: "/leads-pool", icon: <Target size={18} /> },
      {
        id: "inbox",
        label: "Входящие",
        href: "/inbox",
        icon: <Inbox size={18} />,
        badge: inboxPending,
        ariaLabel: `Входящие${inboxPending > 0 ? ` (${inboxPending} ожидают)` : ""}`,
      },
    ];
    if (isAdminOrHead) {
      base.push({ id: "forms",       label: "Формы",         href: "/forms",       icon: <ClipboardList size={18} /> });
      base.push({ id: "automations", label: "Автоматизации", href: "/automations", icon: <Workflow size={18} /> });
    }
    if (isAdmin) {
      base.push({ id: "audit", label: "Журнал", href: "/audit", icon: <History size={18} /> });
    }
    base.push({
      id: "notifications",
      label: "Уведомления",
      icon: <Bell size={18} />,
      badge: unreadCount,
      ariaLabel: `Уведомления${unreadCount > 0 ? ` (${unreadCount} непрочитанных)` : ""}`,
      onClick: () => setNotifOpen(true),
    });
    base.push({ id: "settings", label: "Настройки", href: "/settings", icon: <Settings size={18} /> });
    return base;
  }, [isAdmin, isAdminOrHead, inboxPending, unreadCount]);

  // The active item is whichever route currently matches. Notifications
  // (no href) can never be "active" — only highlighted on hover.
  const activeId = useMemo(() => {
    const match = items.find(
      (it) =>
        it.href && (pathname === it.href || pathname.startsWith(it.href + "/")),
    );
    return match?.id ?? null;
  }, [items, pathname]);

  const highlightedId = hoveredId ?? activeId;

  // Move the pill to the highlighted item. useLayoutEffect runs before
  // paint, so the user never sees the pill at top:0 between mount and
  // the first measurement.
  useLayoutEffect(() => {
    function measure() {
      if (!highlightedId) {
        setPill((p) => ({ ...p, visible: false }));
        return;
      }
      const el = itemRefs.current[highlightedId];
      const nav = navRef.current;
      if (!el || !nav) {
        setPill((p) => ({ ...p, visible: false }));
        return;
      }
      const elRect = el.getBoundingClientRect();
      const navRect = nav.getBoundingClientRect();
      setPill({
        top: elRect.top - navRect.top + nav.scrollTop,
        height: elRect.height,
        visible: true,
      });
    }
    measure();
    // Re-measure when the viewport resizes — Tailwind's `clamp()`-based
    // typography slightly changes row height across breakpoints.
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [highlightedId, items, mobileNavOpen]);

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

  function renderItem(item: NavItem) {
    const isHighlighted = highlightedId === item.id;
    const className = clsx(
      NAV_ROW,
      isHighlighted ? "text-brand-accent-text" : "text-brand-muted",
    );
    const onMouseEnter = () => setHoveredId(item.id);
    const onMouseLeave = () => setHoveredId(null);
    const setRef = (el: HTMLElement | null) => {
      itemRefs.current[item.id] = el;
    };
    const inner = (
      <>
        <span className="relative">
          {item.icon}
          {item.badge != null && item.badge > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[14px] h-[14px] bg-brand-accent text-white text-[9px] font-mono font-bold rounded-full px-1 flex items-center justify-center tabular-nums">
              {item.badge > 99 ? "99+" : item.badge}
            </span>
          )}
        </span>
        {item.label}
      </>
    );

    if (item.href) {
      return (
        <Link
          key={item.id}
          ref={setRef}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          href={item.href as any}
          className={className}
          onMouseEnter={onMouseEnter}
          onMouseLeave={onMouseLeave}
          aria-label={item.ariaLabel}
        >
          {inner}
        </Link>
      );
    }

    return (
      <button
        key={item.id}
        ref={setRef}
        type="button"
        onClick={item.onClick}
        className={`${className} w-full text-left`}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        aria-label={item.ariaLabel}
      >
        {inner}
      </button>
    );
  }

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

        {/* Nav with sliding pill.
            The pill lives inside <nav> as a single absolute element so
            its translateY can be measured against nav's scroll origin.
            Cursor leaving the whole nav also clears `hoveredId` —
            otherwise leaving an item via the gap between rows could
            briefly leave hover state set without a fresh enter event. */}
        <nav
          ref={navRef}
          className="relative flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto"
          onMouseLeave={() => setHoveredId(null)}
        >
          {/* Sliding highlight pill.
              left/right anchors at 12px match nav's px-3 so the pill
              spans the row exactly. Only the transform is animated;
              opacity fade hides the pill when nothing is highlighted
              (e.g., a route not present in the items list). */}
          <div
            aria-hidden
            className="absolute left-3 right-3 top-0 bg-brand-soft rounded-full pointer-events-none"
            style={{
              transform: `translateY(${pill.top}px)`,
              height: pill.height,
              opacity: pill.visible ? 1 : 0,
              transition:
                "transform 200ms cubic-bezier(0.32, 0.72, 0, 1), opacity 150ms ease-out",
            }}
          />

          {items.map(renderItem)}

          {/* Divider */}
          <div className="my-2 border-t border-brand-border" />

          {/* Phase 2 items — disabled, not part of the highlight system */}
          {DISABLED_ITEMS.map((item) => (
            <div
              key={item.id}
              title="Sprint 1.5+"
              className={`${NAV_ROW} text-brand-muted/50 cursor-not-allowed select-none`}
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
