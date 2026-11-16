"""The gemini-decisions adapter of the Decide port (docs/adr/0091 §2):
POST /v1beta/decisions with urllib, the port's yes_no as the API's noul.
MODEL_BASE_URL is the conformance suite's seam (docs/adr/0041 §7), unset
everywhere else."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com"
PLACEHOLDER = "replace-me"
HERE = os.path.dirname(os.path.abspath(__file__))


def model():
    if os.environ.get("GEMINI_DECISIONS_MODEL"):
        return os.environ["GEMINI_DECISIONS_MODEL"]
    with open(os.path.join(HERE, "decide.env"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("GEMINI_DECISIONS_MODEL="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("decide.env names no GEMINI_DECISIONS_MODEL")


def to_api(q):
    out = {"type": "noul" if q["type"] == "yes_no" else q["type"], "instructions": q["instructions"]}
    crit = q.get("criteria")
    if q["type"] == "yes_no":
        if crit:
            out["criteria"] = {f"{k}_description": v for k, v in crit.items()}
    else:
        out["criteria"] = crit
    return out


def from_api(k, a):
    if not isinstance(a, dict):
        raise ValueError(f"answer {k} is not an object")
    if a.get("type") == "noul":
        return {"type": "yes_no", "p_yes": a.get("noul"), "confidence": a.get("confidence")}
    if a.get("type") == "choice":
        return {"type": "choice", "choice": a.get("choice"), "probabilities": a.get("probabilities"),
                "confidence": a.get("confidence")}
    if a.get("type") == "score":
        return {"type": "score", "score": a.get("score"), "probabilities": a.get("probabilities"),
                "confidence": a.get("confidence")}
    raise ValueError(f"answer {k} has type {a.get('type')!r}")


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key or key == PLACEHOLDER:
        print("gemini-decisions: GEMINI_API_KEY is not set in .env; with another provider set DECIDE=structured "
              "(docs/adr/0091 §1)", file=sys.stderr)
        return 1
    try:
        req = json.loads(sys.stdin.read())
        body = {"model": model(), "input": req["input"],
                "questions": {k: to_api(q) for k, q in req["questions"].items()}}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"gemini-decisions: not a Decide request: {exc}", file=sys.stderr)
        return 1
    url = (os.environ.get("MODEL_BASE_URL") or BASE).rstrip("/") + "/v1beta/decisions"
    http = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                  headers={"Content-Type": "application/json", "x-goog-api-key": key})
    began = time.time()
    try:
        with urllib.request.urlopen(http, timeout=float(os.environ.get("DECIDE_TIMEOUT_S", "60"))) as r:  # nosec B310 - https or the suite's loopback
            got = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            err = json.loads(exc.read().decode()).get("error") or {}
        except ValueError:
            err = {}
        print(f"gemini-decisions: HTTP {exc.code}: {err.get('message') or exc.reason}"[:300], file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"gemini-decisions: {url}: {exc}"[:300], file=sys.stderr)
        return 1
    elapsed = time.time() - began
    feedback = got.get("prompt_feedback") or {}
    if feedback.get("block_reason"):
        print(f"gemini-decisions: the input was blocked: {feedback['block_reason']}"
              + (f" ({feedback['block_reason_message']})" if feedback.get("block_reason_message") else ""),
              file=sys.stderr)
        return 1
    try:
        answers = {k: from_api(k, a) for k, a in (got.get("answers") or {}).items()}
    except ValueError as exc:
        print(f"gemini-decisions: {exc}", file=sys.stderr)
        return 1
    usage = got.get("usage") or {}
    print(json.dumps({"answers": answers, "adapter": "gemini-decisions", "provider": "gemini", "model": body["model"],
                      "tokens": {"input": int(usage.get("total_input_tokens") or 0),
                                 "output": int(usage.get("total_output_tokens") or 0)},
                      "duration_s": round(elapsed, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
