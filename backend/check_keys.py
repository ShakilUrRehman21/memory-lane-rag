"""Check that the API keys in .env work: one tiny question per provider, then one real Memory Lane question.

Run with:  test-keys.bat   (or: python backend/check_keys.py)
Keys are never printed.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ai import llm  # noqa: E402
from app.core.config import settings  # noqa: E402

PING = [{"role": "user", "content": "Reply with exactly the word: OK"}]


def explain(err: str) -> str:
    e = err.lower()
    if "401" in e or "invalid" in e or "api key not valid" in e or "unauthenticated" in e or "incorrect api key" in e:
        return "the key was rejected (wrong key, or a key for a different service)"
    if "403" in e or "permission" in e:
        return "the key isn't allowed to use this API (enable the API / billing for that key's project)"
    if "insufficient_quota" in e or "no credits" in e:
        return "the account has no credits left (add billing on the provider's site)"
    if "503" in e or "high demand" in e or "overloaded" in e or "unavailable" in e:
        return "the model is busy right now (temporary); Memory Lane retries and tries a lighter model automatically"
    if "429" in e or "quota" in e or "rate" in e:
        return "quota or rate limit reached (check billing / free-tier limits)"
    if "404" in e:
        return f"model not found; check the model name in .env"
    if "connect" in e or "timeout" in e or "name resolution" in e:
        return "couldn't reach the service (internet, firewall or proxy)"
    return "unexpected error"


def check(name: str, fn) -> bool:
    t = time.time()
    try:
        reply = fn(PING, 0.0, False).strip()
        print(f"  [OK]   {name}: replied {reply[:40]!r} in {time.time() - t:.1f}s")
        return True
    except Exception as exc:
        msg = str(exc).replace(settings.GEMINI_API_KEY or "§", "<key>").replace(settings.OPENAI_API_KEY or "§", "<key>")
        print(f"  [FAIL] {name}: {explain(msg)}")
        print(f"         details: {msg[:240]}")
        return False


def main() -> None:
    print("\nMemory Lane — API key check\n")
    results = {}
    if settings.GEMINI_API_KEY:
        results["gemini"] = check(f"Gemini ({settings.GEMINI_MODEL})", llm._gemini_complete)
        if results["gemini"]:
            kind = "Vertex AI express" if llm._gemini_base == llm.VERTEX_EXPRESS else "Google AI Studio"
            print(f"         using the {kind} endpoint")
    else:
        print("  [--]   Gemini: no GEMINI_API_KEY in .env")
    if settings.OPENAI_API_KEY:
        results["openai"] = check(f"OpenAI-compatible ({settings.OPENAI_MODEL} at {settings.OPENAI_BASE_URL})",
                                  llm._openai_complete)
        if not results["openai"] and not settings.OPENAI_API_KEY.startswith("sk-"):
            print("         note: OpenAI keys start with 'sk-'. If this key is from another provider, set")
            print("         OPENAI_BASE_URL (and OPENAI_MODEL) in .env to that provider's values.")
    else:
        print("  [--]   OpenAI: no OPENAI_API_KEY in .env")
    if settings.OLLAMA_URL:
        results["ollama"] = check(f"Ollama ({settings.OLLAMA_MODEL})", llm._ollama_complete)

    working = [p for p, ok in results.items() if ok]
    print()
    if not working:
        print("No working model, so Memory Lane will keep using the offline writer.\n")
        return

    print(f"Answers will be written by: {llm.provider_label(working[0] if llm.active_provider() not in working else None)}")
    print("\nAsking a real question about the demo archive (Alex Chen)...\n")
    from app.core.database import init_db
    from app.models.schemas import ChatRequest
    from app.storage.repo import Users
    from app.synthesis.answer import answer
    init_db()
    if not Users.get("user_alex"):
        print("  Demo archive not found (start the app once with start.bat, then run this again).")
        return
    q = "When did I start learning machine learning, and why?"
    t = time.time()
    r = answer("user_alex", ChatRequest(query=q))
    print(f"  Q: {q}")
    print(f"  Written by: {r.provider}   ({time.time() - t:.1f}s, {len(r.used_citations)} sources cited)\n")
    for line in r.answer.splitlines():
        print("  " + line)
    print()


if __name__ == "__main__":
    main()
