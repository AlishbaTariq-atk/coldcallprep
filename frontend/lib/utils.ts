import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/** Merge conditional class names, resolving Tailwind class conflicts via tailwind-merge. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
