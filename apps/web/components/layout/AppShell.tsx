"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  CalendarDays,
  Kanban,
  Target,
  Inbox,
  BookOpen,
  Users,
  Settings,
} from "lucide-react";

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

  return (
    <div className="grid min-h-screen bg-canvas" style={{ gridTemplateColumns: "220px 1fr" }}>
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

        {/* Dev user pill */}
        <div className="px-3 py-4 border-t border-black/5">
          <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-canvas">
            <div className="w-7 h-7 rounded-full bg-accent/20 flex items-center justify-center shrink-0">
              <span className="text-[11px] font-bold text-accent">D</span>
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-ink truncate">Dev User</p>
              <p className="text-[10px] font-mono text-muted-3 truncate">dev@drinkx.tech</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Content area — offset by sidebar width */}
      <div className="col-start-2 min-h-screen">
        {children}
      </div>
    </div>
  );
}
