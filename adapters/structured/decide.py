"""The structured adapter of the Decide port (docs/adr/0091 §3): the
profile's model through litellm with a JSON-schema response format. The
model gives probabilities; the port's arithmetic gives the choice, the
score and every confidence. MODEL_BASE_URL is the conformance suite's seam
(docs/adr/0041 §7), unset everywhere else."""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THINKING = "low"


def schema_for(questions):
    def numbers(ids):
        return {"type": "object", "properties": {i: {"type": "number"} for i in ids},
                "required": list(ids), "additionalProperties": False}

    props = {}
    for k, q in questions.items():
        if q["type"] == "yes_no":
            props[k] = numbers(["p_yes"])
        else:
            ids = list(q["criteria"]) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
            props[k] = {"type": "object", "properties": {"probabilities": numbers(ids)},
                        "required": ["probabilities"], "additionalProperties": False}
    return {"type": "object", "properties": props, "required": list(questions), "additionalProperties": False}


def message(req):
    lines = ["=== TEXT ===", req["input"], "=== END ===", "", "Questions:"]
    for k, q in req["questions"].items():
        lines.append(f"- key `{k}`, {q['type'].replace('_', '/')}: {q['instructions']}")
        crit = q.get("criteria")
        if q["type"] == "yes_no" and crit:
            lines += [f"    yes means: {crit['true']}"] if crit.get("true") else []
            lines += [f"    no means: {crit['false']}"] if crit.get("false") else []
        elif q["type"] == "choice":
            lines += [f"    option `{i}`: {d}" for i, d in crit.items()]
        elif q["type"] == "score":
            lines += [f"    level {n}: {d}" for n, d in enumerate(crit)]
    return "\n".join(lines) + "\n"


def normalised(k, raw, ids):
    probs = raw.get("probabilities") if isinstance(raw, dict) else None
    if not isinstance(probs, dict) or set(probs) != set(ids):
        raise ValueError(f"answer {k}: the model gave no probability for every option")
    vals = {i: max(0.0, float(probs[i])) for i in ids}
    total = sum(vals.values())
    if total <= 0:
        raise ValueError(f"answer {k}: the probabilities sum to 0")
    return {i: v / total for i, v in vals.items()}


def answer(q, k, raw):
    """The port's answer from the model's numbers (docs/adr/0091 §1, §3)."""
    if q["type"] == "yes_no":
        p = raw.get("p_yes") if isinstance(raw, dict) else None
        if not isinstance(p, (int, float)) or isinstance(p, bool):
            raise ValueError(f"answer {k}: the model gave no p_yes")
        p = min(0.99, max(0.01, float(p)))
        return {"type": "yes_no", "p_yes": p, "confidence": max(p, 1 - p)}
    if q["type"] == "choice":
        probs = normalised(k, raw, list(q["criteria"]))
        best = max(probs, key=probs.get)
        return {"type": "choice", "choice": best, "probabilities": probs, "confidence": probs[best]}
    levels = [str(i) for i in range(len(q["criteria"]))]
    probs = normalised(k, raw, levels)
    return {"type": "score", "score": sum(int(i) * p for i, p in probs.items()), "probabilities": probs,
            "confidence": max(probs.values())}


def main():
    try:
        from lights_out_adk.model import BadProvider, NoKey, NoModel, ThinkingMapMissing, provider_from_env, thinking_map
        provider, model_id, key = provider_from_env()
        effort = thinking_map(provider, THINKING)
    except (BadProvider, NoKey, NoModel, ThinkingMapMissing) as exc:
        print(f"structured: {exc}", file=sys.stderr)
        return 1
    try:
        req = json.loads(sys.stdin.read())
        questions = req["questions"]
        user = message(req)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"structured: not a Decide request: {exc}", file=sys.stderr)
        return 1
    with open(os.path.join(HERE, "prompt.md"), encoding="utf-8") as fh:
        system = fh.read()
    import litellm  # imported here: the workbench's, as the ADK roles use it (docs/adr/0040 §6)

    litellm.drop_params = True  # a model with no reasoning setting ignores it rather than refusing
    litellm.suppress_debug_info = True
    began = time.time()
    try:
        resp = litellm.completion(
            model=f"{provider}/{model_id}", api_key=key, api_base=os.environ.get("MODEL_BASE_URL") or None,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "decisions", "schema": schema_for(questions), "strict": True}},
            reasoning_effort=effort, timeout=float(os.environ.get("DECIDE_TIMEOUT_S", "120")), num_retries=0)
        text = resp.choices[0].message.content or ""
        raw = json.loads(text)
        answers = {k: answer(q, k, raw.get(k) if isinstance(raw, dict) else None) for k, q in questions.items()}
    except Exception as exc:  # one stderr line, the adapter convention
        print(f"structured: {provider}/{model_id}: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"[:300],
              file=sys.stderr)
        return 1
    usage = getattr(resp, "usage", None)
    print(json.dumps({"answers": answers, "adapter": "structured", "provider": provider,
                      "model": getattr(resp, "model", None) or model_id,
                      "tokens": {"input": int(getattr(usage, "prompt_tokens", 0) or 0),
                                 "output": int(getattr(usage, "completion_tokens", 0) or 0)},
                      "duration_s": round(time.time() - began, 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
