import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

/**
 * Item primitive — composable list row. Drop into surfaces that today
 * hand-roll a flex layout with media (icon/avatar) + title/description +
 * actions. Replaces ~10 ad-hoc layouts across LeadCard contacts,
 * NotesTab entries, TasksTab task rows, NotificationsDrawer items,
 * Team rows, etc.
 *
 *   <Item>
 *     <ItemMedia variant="icon"><User size={16} /></ItemMedia>
 *     <ItemContent>
 *       <ItemTitle>Иван Петров</ItemTitle>
 *       <ItemDescription>Директор по закупкам</ItemDescription>
 *     </ItemContent>
 *     <ItemActions>
 *       <Button variant="ghost" size="sm">Открыть</Button>
 *     </ItemActions>
 *   </Item>
 *
 * <ItemGroup> wraps a list with a thin divider between rows.
 */

const itemVariants = cva(
  "flex items-start gap-3 transition-colors",
  {
    variants: {
      variant: {
        default: "bg-brand-bg rounded-2xl px-3 py-2.5",
        outline: "bg-white border border-brand-border rounded-2xl px-3 py-2.5",
        muted: "bg-brand-panel rounded-2xl px-3 py-2.5",
        inline: "py-2", // for groups with their own dividers
      },
      size: {
        default: "",
        sm: "py-1.5 px-2 gap-2",
      },
      interactive: {
        true: "cursor-pointer hover:bg-brand-bg/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1",
        false: "",
      },
    },
    defaultVariants: { variant: "default", size: "default", interactive: false },
  },
);

export interface ItemProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof itemVariants> {
  asChild?: boolean;
}

const Item = React.forwardRef<HTMLDivElement, ItemProps>(
  ({ className, variant, size, interactive, ...props }, ref) => (
    <div ref={ref} className={cn(itemVariants({ variant, size, interactive, className }))} {...props} />
  ),
);
Item.displayName = "Item";

const ItemMedia = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & {
    variant?: "default" | "icon" | "avatar";
  }
>(({ className, variant = "default", ...props }, ref) => (
  <div
    ref={ref}
    data-variant={variant}
    className={cn(
      "shrink-0 flex items-center justify-center",
      variant === "icon" && "size-8 rounded-full bg-brand-panel text-brand-primary",
      variant === "avatar" && "size-8 rounded-full bg-brand-soft text-brand-accent-text type-caption font-semibold",
      variant === "default" && "mt-0.5 text-brand-muted",
      className,
    )}
    {...props}
  />
));
ItemMedia.displayName = "ItemMedia";

const ItemContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex-1 min-w-0", className)} {...props} />
  ),
);
ItemContent.displayName = "ItemContent";

const ItemTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("type-body text-brand-primary", className)} {...props} />
  ),
);
ItemTitle.displayName = "ItemTitle";

const ItemDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("type-caption text-brand-muted mt-0.5", className)} {...props} />
  ),
);
ItemDescription.displayName = "ItemDescription";

const ItemActions = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("shrink-0 flex items-center gap-1.5", className)} {...props} />
  ),
);
ItemActions.displayName = "ItemActions";

const ItemHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center justify-between gap-2", className)} {...props} />
  ),
);
ItemHeader.displayName = "ItemHeader";

const ItemFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("mt-1", className)} {...props} />
  ),
);
ItemFooter.displayName = "ItemFooter";

const ItemGroup = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col gap-1.5", className)} {...props} />
  ),
);
ItemGroup.displayName = "ItemGroup";

const ItemSeparator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("h-px bg-brand-border", className)} {...props} />
  ),
);
ItemSeparator.displayName = "ItemSeparator";

export {
  Item,
  ItemMedia,
  ItemContent,
  ItemTitle,
  ItemDescription,
  ItemActions,
  ItemHeader,
  ItemFooter,
  ItemGroup,
  ItemSeparator,
  itemVariants,
};
