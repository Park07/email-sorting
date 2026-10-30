#!/usr/bin/env python3
"""Compare matching evaluation reports. No network, models or mailbox access."""

import argparse
import math
from pathlib import Path
import re
import sys

from classifier import CATEGORIES, read_json

FINGERPRINTS = ("fixtures_sha256", "classifier_sha256", "evaluator_sha256", "prompt_sha256")


def validate_report(report):
    if not isinstance(report, dict) or report.get("benchmark_version") != 1:
        raise ValueError("Unsupported report")
    if (report.get("engine_requested") not in {"rules", "groq", "ollama"}
            or type(report.get("evaluation_complete")) is not bool
            or report.get("mailbox_connected") is not False or report.get("mailbox_changes") != 0):
        raise ValueError("Invalid report boundary")
    for key in FINGERPRINTS:
        if not isinstance(report.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", report[key]):
            raise ValueError("Missing provenance")
    model = report.get("requested_model")
    if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,151}", model)):
        raise ValueError("Invalid model identifier")
    total, correct = report.get("cases"), report.get("exact_matches")
    if type(total) is not int or not 1 <= total <= 100 or type(correct) is not int or not 0 <= correct <= total:
        raise ValueError("Invalid counts")
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) != total:
        raise ValueError("Missing results")
    for row in rows:
        if not isinstance(row, dict) or row.get("method") not in {"form-topic", "local-model", "hosted-model", "keyword-hints", "review"}:
            raise ValueError("Invalid result")
    if report["engine_requested"] != "rules":
        allowed = {"form-topic", "hosted-model" if report["engine_requested"] == "groq" else "local-model"}
        if report["evaluation_complete"] != all(row["method"] in allowed for row in rows):
            raise ValueError("Completion contradicts fallback results")
    counts = report.get("per_category")
    if not isinstance(counts, dict) or set(counts) != set(CATEGORIES):
        raise ValueError("Missing category counts")
    for value in counts.values():
        if not isinstance(value, dict):
            raise ValueError("Invalid category counts")
        for key in ("true_positive", "false_positive", "false_negative"):
            if type(value.get(key)) is not int or not 0 <= value[key] <= total:
                raise ValueError("Invalid category counts")
    timing = report.get("timing")
    if not isinstance(timing, dict):
        raise ValueError("Missing timing")
    for key in ("total_seconds", "successful_median_ms", "successful_p95_ms"):
        value = timing.get(key)
        if value is None and key != "total_seconds":
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid timing")
    return report


def comparison(reports):
    for report in reports:
        validate_report(report)
    if len(reports) < 2 or len(reports) > 8:
        raise ValueError("Choose two to eight reports")
    if any(any(row[key] != reports[0][key] for key in FINGERPRINTS) or row["cases"] != reports[0]["cases"] for row in reports[1:]):
        raise ValueError("Cases, code or prompt differ")
    lines = ["| Engine / model | Completed | Exact label agreement | Missed support/refund labels | False spam labels | Response median / p95 | Total time |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in reports:
        name = row["engine_requested"] + (" / " + row["requested_model"] if row["requested_model"] else "")
        complete = row["evaluation_complete"]
        score = f'{row["exact_matches"]}/{row["cases"]} ({100 * row["exact_matches"] / row["cases"]:.1f}%)' if complete else "Incomplete, no model score"
        missed = row["per_category"]["support_refunds"]["false_negative"] if complete else "n/a"
        spam = row["per_category"]["suspected_spam"]["false_positive"] if complete else "n/a"
        timing = row["timing"]
        latency = " / ".join("n/a" if timing[key] is None else f'{timing[key]:.0f} ms' for key in ("successful_median_ms", "successful_p95_ms"))
        lines.append(f'| {name} | {"Yes" if complete else "No"} | {score} | {missed} | {spam} | {latency} | {timing["total_seconds"]:.2f} s |')
    lines.extend(["", "Scores describe these examples only. The bundled set is synthetic, not a production benchmark.",
                  "Model runs include deterministic form-topic hints. Response times cover validated model responses; total time includes pacing and setup.",
                  "An incomplete model run is not ranked. Every message still requires human review."])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        reports = [read_json(path) for path in args.reports]
        print(comparison(reports))
    except (ValueError, OSError, UnicodeError, RecursionError, KeyError, TypeError):
        print("Comparison rejected: use matching reports from the same cases, code and prompt revision.", file=sys.stderr)
        return 2
    return 0 if all(row["evaluation_complete"] for row in reports) else 3


if __name__ == "__main__":
    raise SystemExit(main())
