"""Phase 9 migration: add the 'manager' role to the users check constraint.
Idempotent — safe to run repeatedly. Usage: python -m scripts.migrate_roles"""
import psycopg

from app.config import get_settings

SQL = """
DO $$ BEGIN
  ALTER TABLE app.users DROP CONSTRAINT IF EXISTS users_role_check;
  ALTER TABLE app.users ADD CONSTRAINT users_role_check
      CHECK (role IN ('admin', 'analyst', 'manager'));
END $$;
"""

if __name__ == "__main__":
    with psycopg.connect(get_settings().app_dsn, autocommit=True) as c:
        c.execute(SQL)
    print("roles migration applied: admin | analyst | manager")
