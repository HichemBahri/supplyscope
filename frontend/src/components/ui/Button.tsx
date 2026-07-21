import { clsx } from "clsx";
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost" | "danger" | "navy";

const styles: Record<Variant, string> = {
  primary: "bg-action text-white hover:bg-action-strong",
  navy: "bg-navy-900 text-white hover:bg-navy-800",
  ghost: "bg-transparent text-ink hover:bg-line/60 border border-line",
  danger: "bg-transparent text-danger hover:bg-danger/10 border border-danger/30",
};

export function Button({
  variant = "primary", className, ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium",
        "transition-colors duration-150 disabled:opacity-50 disabled:pointer-events-none",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action",
        styles[variant], className,
      )}
      {...props}
    />
  );
}
