"use client";
import { useMemo } from "react";
import { usePathname } from "next/navigation";
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
  ClipboardList,
  Workflow,
} from "lucide-react";
import { useNotificationsBadge } from "@/lib/hooks/use-notifications";
import { useInboxCount } from "@/lib/hooks/use-inbox";
import { useMe } from "@/lib/hooks/use-me";
import { SidebarNav, type NavItem } from "./SidebarNav";

interface SidebarNavContainerProps {
  onNotificationsClick: () => void;
}

// Owns the polling hooks (notifications badge, inbox count, /me).
// Sits between AppShell and SidebarNav so that 30s polling re-renders
// stop here instead of cascading through AppShell's drawer/search/content.
export function SidebarNavContainer({
  onNotificationsClick,
}: SidebarNavContainerProps) {
  const pathname = usePathname();
  const { data: badge } = useNotificationsBadge();
  const { data: inboxCount } = useInboxCount();
  const { data: me } = useMe();

  const unreadCount = badge?.unread ?? 0;
  const inboxPending = inboxCount?.pending ?? 0;
  const isAdmin = me?.role === "admin";
  const isAdminOrHead = me?.role === "admin" || me?.role === "head";

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
    base.push({
      id: "team",
      label: "Команда",
      href: isAdminOrHead ? "/team" : "/settings?section=team",
      icon: <Users size={18} />,
    });
    base.push({ id: "knowledge", label: "База знаний", href: "/knowledge", icon: <BookOpen size={18} /> });
    if (isAdmin) {
      base.push({ id: "audit", label: "Журнал", href: "/audit", icon: <History size={18} /> });
    }
    base.push({
      id: "notifications",
      label: "Уведомления",
      icon: <Bell size={18} />,
      badge: unreadCount,
      ariaLabel: `Уведомления${unreadCount > 0 ? ` (${unreadCount} непрочитанных)` : ""}`,
      onClick: onNotificationsClick,
    });
    base.push({ id: "settings", label: "Настройки", href: "/settings", icon: <Settings size={18} /> });
    return base;
  }, [isAdmin, isAdminOrHead, inboxPending, unreadCount, onNotificationsClick]);

  // The active item is whichever route currently matches. Notifications
  // (no href) can never be "active" — only highlighted on hover.
  const activeId = useMemo(() => {
    const match = items.find(
      (it) =>
        it.href && (pathname === it.href || pathname.startsWith(it.href + "/")),
    );
    return match?.id ?? null;
  }, [items, pathname]);

  return <SidebarNav items={items} activeId={activeId} />;
}
