/**
 * Merge Tailwind classes safely. Combines clsx's conditional class
 * support with tailwind-merge's conflict resolution so the last class
 * wins for any given Tailwind property.
 *
 * import { cn } from "@/lib/cn";
 * cn("p-2", isActive && "p-4")  // → "p-4"
 */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
