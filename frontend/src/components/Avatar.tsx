/** User avatar with initials fallback (the "anonymous picture by default"). */
import { useState } from "react";
import { clsx } from "clsx";
import { getToken } from "../lib/api";
import type { User } from "../lib/types";

export function Avatar({ user, size = 32, className }:
  { user: Pick<User, "user_id" | "first_name" | "last_name" | "has_avatar">;
    size?: number; className?: string }) {
  const [failed, setFailed] = useState(false);
  const initials = `${user.first_name[0] ?? ""}${user.last_name[0] ?? ""}`.toUpperCase();
  const showImg = user.has_avatar && !failed;
  return showImg ? (
    <img
      src={`/api/users/${user.user_id}/avatar?t=${encodeURIComponent(getToken() ?? "")}`}
      onError={() => setFailed(true)}
      alt={`${user.first_name} ${user.last_name}`}
      width={size} height={size}
      className={clsx("rounded-full object-cover", className)}
      style={{ width: size, height: size }}
    />
  ) : (
    <span
      className={clsx("grid place-items-center rounded-full bg-action/15 font-medium text-action", className)}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden
    >
      {initials || "?"}
    </span>
  );
}
