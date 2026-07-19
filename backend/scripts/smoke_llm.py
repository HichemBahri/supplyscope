"""One-call smoke test of the LLM factory against the real API.

Run from backend/ (module form): uv run python -m scripts.smoke_llm
Cost: a fraction of a cent (fast tier, tiny prompt).
"""
from app.llm.factory import get_llm


def main() -> None:
    llm = get_llm("fast")
    reply = llm.invoke(
        "Reply with exactly: SupplyScope agent factory OK").content
    usage = getattr(getattr(llm, "_last_response", None), "usage", None)
    print(f"Model replied: {reply!r}")
    print("If you can read the OK above, the provider-agnostic factory works.")


if __name__ == "__main__":
    main()
