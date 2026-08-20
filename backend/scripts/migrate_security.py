"""Phase 10 migration: email verification + login lockout columns.
Existing users are grandfathered as verified. Idempotent."""
import psycopg

from app.config import get_settings

SQL = """
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS is_verified boolean NOT NULL DEFAULT true;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS verification_code_hash text;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS verification_expires timestamptz;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS failed_logins integer NOT NULL DEFAULT 0;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS locked_until timestamptz;
"""

if __name__ == "__main__":
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute(SQL)
    print("security migration applied: verification + lockout columns")
