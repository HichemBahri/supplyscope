import { clsx } from "clsx";
import type { InputHTMLAttributes } from "react";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        "w-full rounded-md border border-line bg-card px-3 py-2 text-sm text-ink",
        "placeholder:text-ink-muted/70 transition-colors duration-150",
        "focus:border-action focus:outline-none focus:ring-2 focus:ring-action/20",
        className,
      )}
      {...props}
    />
  );
}
