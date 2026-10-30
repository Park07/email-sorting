#!/usr/bin/env python3
"""Measure label suggestions on supplied examples without connecting to a mailbox."""

import argparse
import hashlib
import json
import getpass
import math
import os
from pathlib import Path
import statistics
import sys
import time
import warnings
from contextlib import contextmanager
from datetime import datetime, timezone

from classifier import CATEGORIES, GROQ_MODEL, MODEL, ROOT, preview_batch, read_json, validate_batch


@contextmanager
def hosted_environment(args, engine):
    """Keep a prompted key in this process only, restoring any previous values."""
    names = ("GROQ_API_KEY", "NXI_GROQ_FREE_TIER_CONFIRMED")
    previous = {name: os.environ.get(name) for name in names}
    try:
        if args.prompt_key or args.confirm_free_tier:
            if engine != "groq" or not args.allow_remote:
                raise ValueError("Hosted setup flags require Groq and explicit remote opt-in")
        if args.confirm_free_tier:
            os.environ[names[1]] = "yes"
        if args.prompt_key:
            if os.environ.get(names[1]) != "yes":
                raise ValueError("Confirm the Free account before entering a key")
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                os.environ[names[0]] = getpass.getpass("Groq API key (hidden, never saved): ")
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def timing_summary(attempts, elapsed, interval):
    successful = sorted(row["duration_ms"] for row in attempts if row["status"] == "success")
    return {
        "total_seconds": round(elapsed, 3),
        "minimum_request_interval_seconds": interval,
        "attempted_requests": len(attempts),
        "successful_requests": len(successful),
        "failed_requests": len(attempts) - len(successful),
        "successful_mean_ms": round(statistics.mean(successful), 3) if successful else None,
        "successful_median_ms": round(statistics.median(successful), 3) if successful else None,
        "successful_p95_ms": successful[math.ceil(len(successful) * .95) - 1] if successful else None,
        "interpretation": "Request time includes HTTP and inference, excludes pacing and local metadata checks. Total time includes both. p95 is nearest-rank on this small sample, not a service-level estimate.",
    }


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
    parser.add_argument("--prompt-key", action="store_true", help="Read a Groq key through a hidden terminal prompt; do not save it")
    parser.add_argument("--confirm-free-tier", action="store_true", help="Acknowledge that you checked the Groq account is on Free; not an API billing check")
    parser.add_argument("--min-interval", type=float, default=None, help="Seconds between request starts, 0 to 60. Default: 10 for Groq, 0 otherwise")
    parser.add_argument("--output", type=Path, help="Save a new report, for example results/groq.json. Existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        cases, emails = load_cases(args.cases)
        engine = args.engine or ("ollama" if args.ollama_url else "rules")
        if args.output is not None and args.output.exists():
            raise ValueError("Output already exists")
        interval = args.min_interval if args.min_interval is not None else (10.0 if engine == "groq" else 0.0)
        attempts = []
        with hosted_environment(args, engine):
            started = time.monotonic()
            results = preview_batch(emails, args.ollama_url, model=args.model, engine=args.engine,
                                    allow_remote=args.allow_remote, telemetry=attempts, min_interval=interval)
            elapsed = time.monotonic() - started
        complete = engine == "rules" or all(row.method in {"form-topic", "local-model", "hosted-model"} for row in results)
        summary = metrics(cases, results)
        summary.update({
            "benchmark_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_complete": complete,
            "score_kind": "rule-baseline" if engine == "rules" else "model-plus-form-hints",
            "engine_requested": engine,
            "requested_model": args.model if engine == "ollama" else GROQ_MODEL if engine == "groq" else None,
            "mailbox_connected": False,
            "mailbox_changes": 0,
            "interpretation": "Examples measure this fixture only. They do not establish production accuracy or authorize automatic actions.",
            "fixtures_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
            "classifier_sha256": hashlib.sha256((ROOT / "classifier.py").read_bytes()).hexdigest(),
            "evaluator_sha256": hashlib.sha256((ROOT / "evaluate.py").read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256((ROOT / "system_prompt.md").read_bytes()).hexdigest(),
            "timing": timing_summary(attempts, elapsed, interval),
            "attempts": attempts,
            "results": [{"id": row.message_id, "method": row.method, "reason": row.reason} for row in results],
        })
        encoded = json.dumps(summary, indent=2) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as destination:
                destination.write(encoded)
    except (ValueError, OSError, UnicodeError, RecursionError, EOFError, getpass.GetPassWarning):
        print("Evaluation rejected. Check input, engine, Free-plan acknowledgement, terminal prompt and a new writable output path. No existing report is overwritten.", file=sys.stderr)
        return 2
    print(encoded, end="")
    # A successful evaluator run is not an accuracy pass. Transport/validation
    # fallbacks must not look like a successful local-model benchmark either.
    if not complete:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
