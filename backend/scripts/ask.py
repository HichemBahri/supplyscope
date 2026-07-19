"""Ask the SupplyScope agent a question from the terminal.

Run from backend/ (module form):
    uv run python -m scripts.ask "Which supplier has the worst on-time delivery rate?"
Options: --tier smart   use the strong model
"""
from __future__ import annotations

import argparse

from app.agent.runner import ask


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("question")
    p.add_argument("--tier", choices=["fast", "smart"], default="fast")
    args = p.parse_args()

    result = ask(args.question, tier=args.tier)

    print("\n─── SQL ───────────────────────────────────────────")
    print(result.sql)
    if result.attempts:
        print(f"\n(self-corrected after {len(result.attempts)} failed attempt(s))")
        for i, a in enumerate(result.attempts, 1):
            print(f"  attempt {i} error: {a['error'][:120]}")
    if not result.failed:
        print(f"\n─── Result: {result.row_count} rows in {result.duration_ms} ms"
              f"{' (truncated)' if result.truncated else ''} ───")
        if result.columns:
            print(" | ".join(result.columns))
            for r in result.rows[:10]:
                print(" | ".join("NULL" if v is None else str(v) for v in r))
            if result.row_count > 10:
                print(f"... ({result.row_count - 10} more rows)")
    print("\n─── Answer ────────────────────────────────────────")
    print(result.answer)


if __name__ == "__main__":
    main()
