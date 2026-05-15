"use client";
import Link from "next/link";
import {
  memo,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { clsx } from "clsx";

export interface NavItem {
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

const DISABLED_ITEMS: DisabledNavItem[] = [];

// Shared row geometry. The pill animates over these — keep paddings and
// gaps consistent across all rows so the pill height stays stable.
const NAV_ROW = "relative z-10 flex items-center gap-3 px-3 py-2 rounded-full font-medium transition-colors duration-200 type-caption focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg";

interface NavItemRowProps {
  item: NavItem;
  isHighlighted: boolean;
  onHover: (id: string | null) => void;
  registerRef: (id: string, el: HTMLElement | null) => void;
}

const NavItemRow = memo(function NavItemRow({
  item,
  isHighlighted,
  onHover,
  registerRef,
}: NavItemRowProps) {
  const handleEnter = useCallback(
    () => onHover(item.id),
    [item.id, onHover],
  );
  const handleLeave = useCallback(() => onHover(null), [onHover]);
  const setRef = useCallback(
    (el: HTMLElement | null) => registerRef(item.id, el),
    [item.id, registerRef],
  );

  // Inactive rows inherit --sidebar-fg via opacity-70 so they stay
  // readable on dark presets (graphite/coffee). Highlighted rows pop
  // with the brand orange — orange has enough contrast on every preset.
  const className = clsx(
    NAV_ROW,
    isHighlighted ? "text-brand-accent-text" : "opacity-70 hover:opacity-100",
  );
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
        ref={setRef}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        href={item.href as any}
        className={className}
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        aria-label={item.ariaLabel}
      >
        {inner}
      </Link>
    );
  }

  return (
    <button
      ref={setRef}
      type="button"
      onClick={item.onClick}
      className={`${className} w-full text-left`}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      aria-label={item.ariaLabel}
    >
      {inner}
    </button>
  );
});

interface SidebarNavProps {
  items: NavItem[];
  activeId: string | null;
}

// Owns hover + sliding-pill state. Lives in its own component so that
// mouseenter/leave events don't re-render the surrounding AppShell tree
// (drawers, search, mobile header, content slot).
export function SidebarNav({ items, activeId }: SidebarNavProps) {
  const navRef = useRef<HTMLElement | null>(null);
  const itemRefs = useRef<Record<string, HTMLElement | null>>({});
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [pill, setPill] = useState<{
    top: number;
    height: number;
    visible: boolean;
  }>({ top: 0, height: 0, visible: false });

  const highlightedId = hoveredId ?? activeId;

  const registerRef = useCallback((id: string, el: HTMLElement | null) => {
    itemRefs.current[id] = el;
  }, []);

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
  }, [highlightedId, items]);

  return (
    <nav
      ref={navRef}
      className="relative flex-1 px-3 py-4 flex flex-col gap-1 overflow-y-auto"
      onMouseLeave={() => setHoveredId(null)}
    >
      {/* Sliding highlight pill.
          left/right anchors at 12px match nav's px-3 so the pill
          spans the row exactly. Only the transform is animated;
          opacity fade hides the pill when nothing is highlighted. */}
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

      {items.map((item) => (
        <NavItemRow
          key={item.id}
          item={item}
          isHighlighted={highlightedId === item.id}
          onHover={setHoveredId}
          registerRef={registerRef}
        />
      ))}

      <div
        style={{ borderTop: "1px solid var(--sidebar-border)" }}
        className="my-2"
      />

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
  );
}
