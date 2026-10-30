"""Hosted and local-provider contracts. All HTTP is mocked; no real keys or mail."""

import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import classifier as c
import evaluate


class Response:
    def __init__(self, value):
        self.raw = json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.raw[:limit]


def hosted_response(categories=None):
    return {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps({"categories": categories or ["workshops"], "needs_review": False})}}]}


class HostedChecks(unittest.TestCase):
    def setUp(self):
        self.email = c.Email("fixture-1", "A question", "Can our children attend?")
        env = patch.dict(os.environ, {"GROQ_API_KEY": "synthetic-test-value", "NXI_GROQ_FREE_TIER_CONFIRMED": "yes"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_hosted_requires_batch_opt_in_even_with_key(self):
        with patch("classifier.build_opener", side_effect=AssertionError("Network must not run")):
            with self.assertRaises(ValueError):
                c.preview_batch([self.email], engine="groq")

    def test_hosted_requires_explicit_free_account_confirmation(self):
        with patch.dict(os.environ, {"NXI_GROQ_FREE_TIER_CONFIRMED": "no"}), \
                patch("classifier.build_opener", side_effect=AssertionError("Network must not run")):
            with self.assertRaises(ValueError):
                c.preview_batch([self.email], engine="groq", allow_remote=True)

    def test_missing_or_malformed_key_is_rejected_before_request(self):
        for key in ("", "secret\nInjected: header", "token\t", "秘密"):
            with patch.dict(os.environ, {"GROQ_API_KEY": key}), \
                    patch("classifier.build_opener", side_effect=AssertionError("Network must not run")):
                with self.assertRaises(ValueError):
                    c.call_groq(self.email, allow_remote=True)

    def test_selected_engine_is_not_changed_by_present_credentials(self):
        with patch("classifier.call_groq", side_effect=AssertionError("Unexpected hosted call")):
            result = c.preview_batch([self.email])
        self.assertEqual(result[0].method, "review")

    def test_hosted_request_has_fixed_endpoint_and_no_tools(self):
        with patch("classifier.build_opener") as factory:
            factory.return_value.open.return_value = Response(hosted_response())
            categories, _ = c.call_groq(self.email, allow_remote=True)
        request = factory.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, c.GROQ_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-value")
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["model"], c.GROQ_MODEL)
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(factory.call_args.args[0].proxies, {})
        self.assertIsInstance(factory.call_args.args[1], c.NoRedirect)
        self.assertEqual(categories, ["workshops"])

    def test_rate_limit_preserves_all_messages_and_no_provider_switch(self):
        with patch("classifier.build_opener") as factory, \
                patch("classifier.call_model", side_effect=AssertionError("Must not switch to Eye")):
            factory.return_value.open.side_effect = HTTPError(c.GROQ_URL, 429, "raw private response", {}, None)
            results = c.preview_batch([self.email, c.Email("fixture-2", "Refund", "Please help")], engine="groq", allow_remote=True)
        self.assertEqual(factory.return_value.open.call_count, 1)
        self.assertEqual([row.message_id for row in results], ["fixture-1", "fixture-2"])
        self.assertTrue(all(row.review_required for row in results))
        self.assertNotIn("raw private", str(results))

    def test_model_action_fields_and_system_labels_are_rejected(self):
        for decision in ({"categories": ["TRASH"], "needs_review": False},
                         {"categories": ["workshops"], "needs_review": False, "send": True}):
            response = hosted_response()
            response["choices"][0]["message"]["content"] = json.dumps(decision)
            with self.assertRaises(c.InvalidModelOutput):
                c.parse_groq_response(json.dumps(response))

    def test_refusals_tool_calls_and_truncation_rejected(self):
        for key, value in (("tool_calls", [{}]), ("function_call", {"name": "send"}), ("refusal", "Cannot classify")):
            response = hosted_response()
            response["choices"][0]["message"][key] = value
            with self.assertRaises(c.InvalidModelOutput):
                c.parse_groq_response(json.dumps(response))
        response = hosted_response()
        response["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(c.InvalidModelOutput):
            c.parse_groq_response(json.dumps(response))

    def test_hosted_report_never_contains_key_or_message_text(self):
        with patch("classifier.call_groq", return_value=(["workshops"], False)):
            result = c.preview_batch([self.email], engine="groq", allow_remote=True)
        value = json.dumps(c.report(result, "groq"))
        self.assertNotIn("synthetic-test-value", value)
        self.assertNotIn(self.email.body, value)
        self.assertTrue(result[0].review_required)

    def test_cli_and_evaluator_report_failed_inference_with_exit_three(self):
        with patch("classifier.call_groq", side_effect=c.ModelUnavailable("Hosted model offline")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(["--engine", "groq", "--allow-remote"]), 3)
            self.assertEqual(evaluate.main(["--engine", "groq", "--allow-remote"]), 3)


class LocalMetadataChecks(unittest.TestCase):
    def model(self, **extra):
        return {"name": c.MODEL, "digest": "fixture-digest", "details": {"format": "gguf"}, **extra}

    def test_model_check_sends_no_email_and_returns_digest(self):
        with patch("classifier.build_opener") as factory:
            factory.return_value.open.return_value = Response({"models": [self.model()]})
            metadata = c.inspect_local_model("http://localhost:11434", c.MODEL)
        request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.full_url, "http://localhost:11434/api/tags")
        self.assertEqual(metadata["digest"], "fixture-digest")

    def test_remote_alias_missing_model_and_unknown_metadata_are_blocked(self):
        for models in ([self.model(remote_host="https://ollama.com")], [self.model(remote_model="remote")],
                       [self.model(details={})], [self.model(digest="")], []):
            with patch("classifier.build_opener") as factory:
                factory.return_value.open.return_value = Response({"models": models})
                with self.assertRaises(c.ModelUnavailable):
                    c.inspect_local_model("http://localhost", c.MODEL)

    def test_preflight_failure_blocks_inference(self):
        with patch("classifier.inspect_local_model", side_effect=c.ModelUnavailable("Model not local")), \
                patch("classifier.call_model", side_effect=AssertionError("Email must not be sent")):
            result = c.preview_batch([c.Email("test-1", "Question", "Hello")], "http://localhost")
        self.assertEqual(result[0].method, "review")

    def test_cloud_names_and_url_model_names_rejected(self):
        for model in ("qwen-cloud", "https://remote/model", "model\nother", ""):
            with self.assertRaises(ValueError):
                c.validate_model_name(model)

    def test_alternative_local_chat_model_is_selectable(self):
        payload = c.model_payload(c.Email("test-1", "Hi", "Hello"), "example-local:4b")
        self.assertEqual(payload["model"], "example-local:4b")


if __name__ == "__main__":
    unittest.main()
