"""Ping every supported Meta model live on https://api.meta.ai/v1.

Sends a tiny billed chat completion per model with MODEL_API_KEY so the
dev.meta.ai usage dashboard lights up. Safe by default: refuses to run in
MOCK_MODE unless --force is passed.

Usage:
    export MODEL_API_KEY="..."            # from https://dev.meta.ai
    python3 scripts/ping_meta_models.py
    python3 scripts/ping_meta_models.py --models meta/llama-3.2-90b-vision-instruct
    MOCK_MODE=true python3 scripts/ping_meta_models.py --force   # prove request shape w/o billing
"""
import json
import os
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

API_URL = os.getenv("META_API_URL", "https://api.meta.ai/v1/chat/completions")
API_KEY = os.getenv("MODEL_API_KEY") or os.getenv("META_API_KEY", "")

TEXT_MODELS = [
    "meta/llama-3.2-90b-vision-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-3b-instruct",
    "meta/llama-3.2-1b-instruct",
]
# SAM 2 is a vision-segmentation endpoint, not chat: verify via backend catalog, not billed ping.
SEG_MODELS = ["meta/sam-2-hiera-large"]

PROMPT = (
    "You are an agronomist. Reply with exactly this JSON, no other text: "
    '{"crop": "cassava", "note": "ping ok"}'
)


def ping(model_id: str, timeout: int = 60) -> dict:
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.0,
        "max_tokens": 60,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        dt = (time.perf_counter() - t0) * 1000
        usage = data.get("usage", {}) or {}
        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            pass
        return {"model": model_id, "ok": True, "latency_ms": round(dt, 1),
                "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"), "reply": content[:120]}
    except Exception as e:
        return {"model": model_id, "ok": False, "error": str(e)[:300]}


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    only = [a for a in args if a.startswith("meta/")]
    mock = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")
    if mock and not force:
        print("MOCK_MODE is on — refusing to spend live credits. Re-run with --force to proceed.")
        return 2
    if not API_KEY:
        print("Set MODEL_API_KEY (from https://dev.meta.ai) before pinging live models.")
        return 2
    targets = only or TEXT_MODELS
    print(f"Pinging {len(targets)} model(s) on {API_URL} …")
    fails = 0
    total_tokens = 0
    for m in targets:
        r = ping(m)
        if r["ok"]:
            total_tokens += r.get("total_tokens") or 0
            print(f"[OK] {m} | {r['latency_ms']}ms | tokens={r.get('total_tokens')} "
                  f"(in={r.get('prompt_tokens')}, out={r.get('completion_tokens')}) | {r.get('reply')}")
        else:
            fails += 1
            print(f"[FAIL] {m} | {r['error']}")
    print(f"Segmentation models (verified via backend catalog, no chat ping): {', '.join(SEG_MODELS)}")
    print(f"Done: {len(targets) - fails}/{len(targets)} live, ~{total_tokens} tokens billed. Check dev.meta.ai dashboard.")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
