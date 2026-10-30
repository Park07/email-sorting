"""Benchmark integrity checks. All inference and terminal prompts are mocked."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import classifier as c
import compare
import evaluate


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def baseline(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(evaluate.main([]), 0)
        return json.loads(output.getvalue())

    def test_timing_excludes_skipped_form_messages_and_keeps_failed_attempts(self):
        emails = [c.Email("form-1", "NXI website enquiry: Workshop", "Dates?"),
                  c.Email("one", "Question", "Hello"), c.Email("two", "Question", "Hello")]
        attempts = []
        with patch("classifier.groq_key", return_value="fixture-only"), \
                patch("classifier.call_groq", side_effect=[(["workshops"], False), c.InvalidModelOutput("Rejected")]), \
                patch("classifier.time.monotonic", side_effect=[0, .125, 1, 1.5]):
            rows = c.preview_batch(emails, engine="groq", allow_remote=True, telemetry=attempts)
        self.assertEqual([row["duration_ms"] for row in attempts], [125, 500])
        self.assertEqual([row["status"] for row in attempts], ["success", "invalid-output"])
        self.assertEqual(rows[0].method, "form-topic")
        self.assertNotIn("Hello", json.dumps(attempts))

    def test_pacing_only_applies_between_actual_model_attempts(self):
        emails = [c.Email("one", "Hi", "Hello"), c.Email("two", "Hi", "Hello")]
        with patch("classifier.groq_key", return_value="fixture-only"), \
                patch("classifier.call_groq", return_value=([], True)), \
                patch("classifier.time.monotonic", return_value=10), patch("classifier.time.sleep") as sleep:
            c.preview_batch(emails, engine="groq", allow_remote=True, min_interval=3)
        sleep.assert_called_once_with(3)

    def test_prompted_key_is_removed_after_transport_failure(self):
        with patch("evaluate.getpass.getpass", return_value="fictional-key"), \
                patch("classifier.call_groq", side_effect=c.ModelUnavailable("Hosted model offline")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = evaluate.main(["--engine", "groq", "--allow-remote", "--confirm-free-tier", "--prompt-key"])
        self.assertEqual(code, 3)
        self.assertNotIn("GROQ_API_KEY", os.environ)
        self.assertNotIn("NXI_GROQ_FREE_TIER_CONFIRMED", os.environ)
        self.assertNotIn("fictional-key", output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["evaluation_complete"])

    def test_existing_output_is_preserved_before_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text("keep this")
            with patch("evaluate.preview_batch", side_effect=AssertionError("No inference")), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(evaluate.main(["--output", str(path)]), 2)
            self.assertEqual(path.read_text(), "keep this")

    def test_reports_with_different_prompt_or_cases_cannot_be_compared(self):
        baseline = self.baseline()
        for field in compare.FINGERPRINTS:
            other = copy.deepcopy(baseline)
            other[field] = "0" * 64
            with self.assertRaises(ValueError):
                compare.comparison([baseline, other])

    def test_failed_inference_is_not_presented_as_a_model_accuracy_score(self):
        baseline = self.baseline()
        with patch("classifier.groq_key", return_value="fixture-only"), \
                patch("classifier.call_groq", side_effect=c.ModelUnavailable("Model offline")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(evaluate.main(["--engine", "groq", "--allow-remote"]), 3)
        failed = json.loads(output.getvalue())
        table = compare.comparison([baseline, failed])
        self.assertIn("Incomplete, no model score", table)
        failed["evaluation_complete"] = True
        with self.assertRaises(ValueError):
            compare.comparison([baseline, failed])

    def test_no_model_run_has_no_invented_response_latency(self):
        baseline = self.baseline()
        self.assertEqual(baseline["timing"]["attempted_requests"], 0)
        self.assertIsNone(baseline["timing"]["successful_median_ms"])
        self.assertIn("n/a / n/a", compare.comparison([baseline, baseline]))

    def test_nonfinite_pacing_is_rejected_before_network(self):
        with patch("classifier.call_groq", side_effect=AssertionError("No network")):
            for interval in (float("nan"), float("inf"), -1, 61):
                with self.assertRaises(ValueError):
                    c.preview_batch([c.Email("one", "Hi", "Hello")], min_interval=interval)


if __name__ == "__main__":
    unittest.main()
