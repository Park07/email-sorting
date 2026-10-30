#!/usr/bin/env python3
"""Measure label suggestions on supplied examples without connecting to a mailbox."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from classifier import CATEGORIES, GROQ_MODEL, MODEL, ROOT, preview_batch, read_json, validate_batch


def load_cases(path):
    cases = read_json(path)
    if not isinstance(cases, list):
        raise ValueError("Expected an array of evaluation cases")
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"email", "expected_categories", "note"}
                or not isinstance(case["note"], str)):
            raise ValueError("Invalid evaluation case")
        expected = case["expected_categories"]
        if (not isinstance(expected, list) or any(not isinstance(key, str) or key not in CATEGORIES for key in expected)
                or len(expected) != len(set(expected))):
            raise ValueError("Invalid expected categories")
    emails = validate_batch([case["email"] for case in cases])
    return cases, emails


def metrics(cases, results):
    if len(cases) != len(results) or any(case["email"]["id"] != result.message_id for case, result in zip(cases, results)):
        raise ValueError("Results must match every evaluation case in order")
    counts = {key: {"true_positive": 0, "false_positive": 0, "false_negative": 0} for key in CATEGORIES}
    mismatches = []
    for case, result in zip(cases, results):
        expected, actual = set(case["expected_categories"]), set(result.categories)
        for category in CATEGORIES:
            if category in expected and category in actual:
                counts[category]["true_positive"] += 1
            elif category in actual:
                counts[category]["false_positive"] += 1
            elif category in expected:
                counts[category]["false_negative"] += 1
        if actual != expected:
            mismatches.append({"id": result.message_id, "expected": sorted(expected), "suggested": sorted(actual)})
    for count in counts.values():
        tp, fp, fn = count["true_positive"], count["false_positive"], count["false_negative"]
        count["precision"] = round(tp / (tp + fp), 4) if tp + fp else None
        count["recall"] = round(tp / (tp + fn), 4) if tp + fn else None
    total = len(results)
    return {
        "cases": total,
        "exact_matches": total - len(mismatches),
        "exact_match_percent": round(100 * (total - len(mismatches)) / total, 1) if total else None,
        "review_percent": round(100 * sum(result.review_required for result in results) / total, 1) if total else None,
        "model_classified": sum(result.method == "local-model" for result in results),
        "hosted_classified": sum(result.method == "hosted-model" for result in results),
        "per_category": counts,
        "mismatches": mismatches,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "fixtures/evaluation.json")
    parser.add_argument("--ollama-url", help="Opt in to inference on your local Ollama server")
    parser.add_argument("--engine", choices=["rules", "ollama", "groq"])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    try:
        cases, emails = load_cases(args.cases)
        results = preview_batch(emails, args.ollama_url, model=args.model, engine=args.engine, allow_remote=args.allow_remote)
        engine = args.engine or ("ollama" if args.ollama_url else "rules")
        summary = metrics(cases, results)
        summary.update({
            "engine_requested": engine,
            "requested_model": args.model if engine == "ollama" else GROQ_MODEL if engine == "groq" else None,
            "mailbox_connected": False,
            "mailbox_changes": 0,
            "interpretation": "Examples measure this fixture only. They do not establish production accuracy or authorize automatic actions.",
            "fixtures_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
            "classifier_sha256": hashlib.sha256((ROOT / "classifier.py").read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256((ROOT / "system_prompt.md").read_bytes()).hexdigest(),
            "results": [{"id": row.message_id, "method": row.method, "reason": row.reason} for row in results],
        })
    except (ValueError, OSError, UnicodeError, RecursionError):
        print("Evaluation input/configuration rejected. Check the documented schema and limits.", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    # A successful evaluator run is not an accuracy pass. Transport/validation
    # fallbacks must not look like a successful local-model benchmark either.
    if engine != "rules" and any(row.method not in {"form-topic", "local-model", "hosted-model"} for row in results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
