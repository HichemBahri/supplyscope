# v1.0.8 — ghost test dashboards: admin moderation, visible errors, self-cleaning tests

Why it happened: the test suite registers fixture users ("Dana Karray", e-mails
d-xxxx@example.com) and creates shared boards, and never removed them; the
frontend showed the delete icon to admins, but the backend allowed only the
owner (403), and the page swallowed the error, so nothing seemed to happen.

Three files, overwrite:
- backend/app/api/routes_dashboards.py   an administrator may delete any dashboard
                                          (audited as dashboard.deleted_by_admin)
- backend/tests/test_dashboards.py       client fixture deletes every board it created;
                                          new test: admin can delete another user's board,
                                          another analyst cannot
- frontend/src/pages/Dashboards.tsx      a failed deletion shows its reason

One-off cleanup of the boards already there (make psql, then):

    DELETE FROM app.dashboards   WHERE owner_id IN (SELECT user_id FROM app.users WHERE email LIKE '%@example.com');
    DELETE FROM app.saved_charts WHERE user_id  IN (SELECT user_id FROM app.users WHERE email LIKE '%@example.com');
    -- optional, if none of YOUR accounts uses an @example.com address:
    -- DELETE FROM app.users WHERE email LIKE '%@example.com' AND role <> 'admin';

Then:  cd backend && uv run pytest tests/test_dashboards.py tests/test_users_admin.py -q   # 10 passed
       restart the backend and the frontend
       git add -A && git commit -m "Dashboards: admin moderation, self-cleaning tests (v1.0.8)" && git tag v1.0.8
