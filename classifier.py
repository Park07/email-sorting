#!/usr/bin/env python3
"""Preview NXI email labels. Standard library only. No mailbox integration."""

import argparse
from dataclasses import asdict, dataclass, replace
from http.client import HTTPException
import ipaddress
import json
import os
import math
import time
from pathlib import Path
import re
import sys
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent
MODEL = "qwen3.5:4b"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_FILE_BYTES = 2_000_000
MAX_BATCH = 100
CATEGORIES = {
    "workshops": "NXI/Workshops",
    "schools_quotes": "NXI/Schools and quotes",
    "products_engineering": "NXI/Products and engineering",
    "orders_delivery": "NXI/Orders and delivery",
    "support_refunds": "NXI/Support and refunds",
    "suppliers_invoices": "NXI/Suppliers and invoices",
    "suspected_spam": "NXI/Suspected spam",
}
REVIEW_LABEL = "NXI/Needs review"
FORM_TOPICS = {
    "workshop": ("workshops",),
    "school workshop": ("workshops", "schools_quotes"),
    "products and school pricing": ("products_engineering", "schools_quotes"),
    "engineering": ("products_engineering",),
}
RULES = {
    "workshops": r"\b(workshops?|holiday programmes?|holiday programs?|robotics classes|coding classes)\b",
    "schools_quotes": r"\b(schools?|bulk|group (?:quote|pricing|discount)|class of \d+)\b",
    "products_engineering": r"\b(soradrive|sensor bars?|controller boards?|pcbs?|firmware|engineering design|mechanical design)\b",
    "orders_delivery": r"\b(shipping|delivery|back[ -]?orders?|restock|tracking|dispatch|eta|order (?:status|number))\b|\border\s*#\s*\w+",
    "support_refunds": r"\b(refunds?|cancellations?|cancel|cancelled|canceled|faulty|broken|not working|doesn't work|charged twice)\b",
    "suppliers_invoices": r"\b(invoices?|suppliers?|vendors?|purchase orders?)\b",
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)},
                       "uniqueItems": True, "maxItems": len(CATEGORIES)},
        "needs_review": {"type": "boolean"},
    },
    "required": ["categories", "needs_review"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Email:
    id: str
    subject: str
    body: str


@dataclass(frozen=True)
class Suggestion:
    message_id: str
    categories: tuple[str, ...]
    labels: tuple[str, ...]
    method: str
    review_required: bool
    reason: str


class ModelUnavailable(Exception):
    """Transport failed. Keep previews available and stop further inference this run."""


class InvalidModelOutput(Exception):
    """The model response cannot be trusted as a classification."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_json(text):
    return json.loads(text, object_pairs_hook=_unique_object)


def read_json(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Input exceeds the 2 MB limit")
    return parse_json(raw.decode("utf-8"))


def validate_email(value):
    if not isinstance(value, dict) or set(value) != {"id", "subject", "body"}:
        raise ValueError("Each email must contain only id, subject and plain-text body")
    if not isinstance(value["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", value["id"]):
        raise ValueError("Use a unique opaque id of 1 to 100 letters, digits, dots, colons, hyphens or underscores")
    for key, limit in (("subject", 1000), ("body", 8000)):
        text = value[key]
        if not isinstance(text, str) or len(text.encode("utf-8")) > limit:
            raise ValueError(f"{key} must be text, at most {limit} UTF-8 bytes")
    return Email(**value)


def validate_batch(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_BATCH:
        raise ValueError(f"Input must be an array of 1 to {MAX_BATCH} emails")
    emails = [validate_email(item) for item in value]
    if len({item.id for item in emails}) != len(emails):
        raise ValueError("Duplicate email IDs: use one current message per ID")
    return emails


def normalise(text):
    return unicodedata.normalize("NFKC", text).casefold()


def current_body(body):
    """Conservative English reply-history heuristic, not a MIME or language parser."""
    kept = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^(on .+wrote:|[- ]*original message[- ]*|begin forwarded message:)$", stripped, re.I):
            break
        if not stripped.startswith(">"):
            kept.append(line)
    return "\n".join(kept)


def suggestion(email, categories, method, reason):
    # All v1 output requires human review, even when the model claims certainty.
    # Only this fixed list can become a label. No system mailbox labels are allowed.
    ordered = tuple(key for key in CATEGORIES if key in categories)
    return Suggestion(email.id, ordered, tuple(CATEGORIES[key] for key in ordered) + (REVIEW_LABEL,),
                      method, True, reason)


def rule_preview(email):
    subject = normalise(email.subject).strip()
    prefix = "nxi website enquiry: "
    topic = subject[len(prefix):] if subject.startswith(prefix) else None
    topic_labels = FORM_TOPICS.get(topic, ())
    text = normalise(email.subject + "\n" + current_body(email.body))
    found = {key for key, pattern in RULES.items() if re.search(pattern, text)}
    found.update(topic_labels)
    if ("guaranteed returns" in text and re.search(r"\b(crypto|bitcoin)\b", text)) or (
        "won the lottery" in text and "claim fee" in text
    ):
        found.add("suspected_spam")
    if topic_labels:
        return suggestion(email, found, "form-topic", "Subject topic plus keyword hints; sender authenticity is not verified")
    if found:
        return suggestion(email, found, "keyword-hints", "Keywords are hints, not a confirmed booking, order or payment")
    return suggestion(email, (), "review", "No reliable topic hint; review the original message")


def local_endpoint(value):
    """Allow explicit loopback/RFC1918 addresses only. No DNS, credentials or redirects."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port if parsed.port is not None else 11434
    except ValueError:
        raise ValueError("Invalid local Ollama address") from None
    if (any(character.isspace() for character in value) or parsed.scheme not in {"http", "https"} or not host or parsed.username is not None
            or parsed.password is not None or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or not 1 <= port <= 65535):
        raise ValueError("Use a local Ollama base URL without credentials, paths, queries or fragments")
    if host != "localhost":
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError("Use localhost or a literal loopback/private IPv4 address") from None
        networks = [ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
        if not address.is_loopback and not any(address in net for net in networks):
            raise ValueError("Public, link-local and shared-network addresses are not allowed")
    host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{host}:{port}/api/chat"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_model_name(model):
    if (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,150}", model)
            or "://" in model or "cloud" in model.casefold()):
        raise ValueError("Use an installed local model name, not a URL or cloud model")
    return model


def model_payload(email, model=MODEL):
    prompt = (ROOT / "system_prompt.md").read_text(encoding="utf-8")
    return {
        "model": validate_model_name(model),
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"subject": email.subject, "body": current_body(email.body)}, ensure_ascii=False)},
        ],
        "format": OUTPUT_SCHEMA,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 256},
    }


def validate_decision(decision):
    if not isinstance(decision, dict) or set(decision) != {"categories", "needs_review"}:
        raise ValueError("Unexpected decision fields")
    categories = decision["categories"]
    if (not isinstance(categories, list) or len(categories) > len(CATEGORIES)
            or any(not isinstance(key, str) or key not in CATEGORIES for key in categories)
            or len(categories) != len(set(categories)) or type(decision["needs_review"]) is not bool):
        raise ValueError("Invalid decision values")
    return categories, decision["needs_review"]


def parse_model_response(raw):
    try:
        envelope = parse_json(raw)
        if (not isinstance(envelope, dict) or envelope.get("done") is not True
                or envelope.get("done_reason") != "stop"):
            raise ValueError("Incomplete response")
        message = envelope.get("message")
        if (not isinstance(message, dict) or message.get("role") != "assistant"
                or message.get("tool_calls") or not isinstance(message.get("content"), str)):
            raise ValueError("Invalid assistant message")
        if envelope.get("remote_host") or envelope.get("remote_model"):
            raise ValueError("Unexpected remote-model response")
        return validate_decision(parse_json(message["content"]))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InvalidModelOutput("Model output failed validation; review the email") from None


def inspect_local_model(endpoint, model):
    """Read installed model metadata before sending any message text to Ollama."""
    validate_model_name(model)
    target = local_endpoint(endpoint).removesuffix("/chat") + "/tags"
    request = Request(target, method="GET")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            raw = response.read(262_145)
        if len(raw) > 262_144:
            raise ValueError("Metadata too large")
        listing = parse_json(raw)
        if not isinstance(listing, dict) or not isinstance(listing.get("models"), list):
            raise ValueError("Invalid metadata")
        wanted = model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"
        for candidate in listing["models"]:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            if name not in {model, wanted}:
                continue
            if (candidate.get("remote_host") or candidate.get("remote_model")
                    or not isinstance(candidate.get("details"), dict)
                    or candidate["details"].get("format") != "gguf"
                    or not isinstance(candidate.get("digest"), str) or not candidate["digest"]):
                raise ValueError("Model is not verified as local")
            return {"name": name, "digest": candidate["digest"]}
        raise ValueError("Model not installed")
    except (URLError, OSError, HTTPException, ValueError, TypeError, UnicodeError, RecursionError):
        raise ModelUnavailable("Local model metadata unavailable or not local; no email sent to model") from None


def call_model(email, endpoint, model=MODEL):
    # This request is only to the operator-selected local model.
    # Proxy variables and redirects are disabled so email text cannot follow them elsewhere.
    target = local_endpoint(endpoint)
    request = Request(target, data=json.dumps(model_payload(email, model)).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=45) as response:
            raw = response.read(16_385)
    except (URLError, OSError, HTTPException):
        raise ModelUnavailable("Local model unavailable; retained keyword preview for review") from None
    if len(raw) > 16_384:
        raise InvalidModelOutput("Model response exceeded the size limit")
    return parse_model_response(raw)


def groq_key(allow_remote):
    if not allow_remote:
        raise ValueError("Hosted inference requires explicit --allow-remote")
    if os.environ.get("NXI_GROQ_FREE_TIER_CONFIRMED") != "yes":
        raise ValueError("Confirm the Groq account is on Free before using the hosted adapter")
    key = os.environ.get("GROQ_API_KEY", "")
    if not key or len(key) > 4096 or not key.isascii() or any(character.isspace() for character in key):
        raise ValueError("GROQ_API_KEY is missing or malformed")
    return key


def groq_payload(email):
    # Keep the provider schema within its documented subset, then enforce all
    # extra constraints again with validate_decision after the response.
    schema = parse_json(json.dumps(OUTPUT_SCHEMA))
    schema["properties"]["categories"].pop("uniqueItems", None)
    schema["properties"]["categories"].pop("maxItems", None)
    return {
        "model": GROQ_MODEL,
        "messages": model_payload(email)["messages"],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "nxi_email_labels", "strict": True, "schema": schema}},
        "temperature": 0,
        "reasoning_effort": "low",
        "max_completion_tokens": 512,
        "stream": False,
    }


def parse_groq_response(raw):
    try:
        response = parse_json(raw)
        if not isinstance(response, dict):
            raise ValueError("Invalid response")
        choices = response.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError("Invalid choices")
        choice = choices[0]
        message = choice.get("message")
        if (choice.get("finish_reason") != "stop" or not isinstance(message, dict)
                or message.get("role") != "assistant" or message.get("tool_calls")
                or message.get("function_call") or message.get("refusal")
                or not isinstance(message.get("content"), str)):
            raise ValueError("Incomplete or invalid completion")
        return validate_decision(parse_json(message["content"]))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InvalidModelOutput("Hosted model output failed validation; review the email") from None


def call_groq(email, allow_remote=False):
    key = groq_key(allow_remote)
    request = Request(GROQ_URL, data=json.dumps(groq_payload(email)).encode("utf-8"),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + key}, method="POST")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(65_537)
    except HTTPError as error:
        reason = "Hosted model rate-limited; remaining messages kept for review" if error.code == 429 else "Hosted model request failed; remaining messages kept for review"
        raise ModelUnavailable(reason) from None
    except (URLError, OSError, HTTPException):
        raise ModelUnavailable("Hosted model unavailable; remaining messages kept for review") from None
    if len(raw) > 65_536:
        raise InvalidModelOutput("Hosted model response exceeded the size limit")
    return parse_groq_response(raw)


def preview_batch(emails, ollama_url=None, *, model=MODEL, engine=None, allow_remote=False,
                  telemetry=None, min_interval=0.0):
    engine = engine or ("ollama" if ollama_url is not None else "rules")
    if engine not in {"rules", "ollama", "groq"}:
        raise ValueError("Unknown engine")
    if (isinstance(min_interval, bool) or not isinstance(min_interval, (int, float))
            or not math.isfinite(min_interval) or not 0 <= min_interval <= 60):
        raise ValueError("Request interval must be between zero and sixty seconds")
    if telemetry is not None and not isinstance(telemetry, list):
        raise ValueError("Telemetry must be a list")
    if engine != "ollama" and ollama_url is not None:
        raise ValueError("Ollama address is only valid with the Ollama engine")
    if engine == "ollama" and ollama_url is None:
        raise ValueError("Ollama requires an explicit local URL")
    if engine == "groq":
        groq_key(allow_remote)  # Fail before any request, including form-only batches.
    if ollama_url is not None:
        local_endpoint(ollama_url)  # Validate before processing anything.
        validate_model_name(model)
    model_available = engine != "rules"
    model_checked = False
    last_started = None
    results = []
    for email in emails:
        fallback = rule_preview(email)
        if engine == "rules" or fallback.method == "form-topic":
            results.append(fallback)
            continue
        if not model_available:
            results.append(replace(fallback, reason="Model paused after a connection failure; keyword preview only"))
            continue
        started = None
        attempt_status = "unavailable"
        try:
            if engine == "ollama":
                if not model_checked:
                    inspect_local_model(ollama_url, model)
                    model_checked = True
            if last_started is not None and min_interval:
                remaining = min_interval - (time.monotonic() - last_started)
                if remaining > 0:
                    time.sleep(remaining)
            started = last_started = time.monotonic()
            if engine == "ollama":
                categories, uncertain = call_model(email, ollama_url, model)
            else:
                categories, uncertain = call_groq(email, allow_remote=allow_remote)
            attempt_status = "success"
            results.append(suggestion(email, categories, "local-model" if engine == "ollama" else "hosted-model",
                                      "Model requested review" if uncertain else "Model suggestion; not yet evaluated on NXI mail"))
        except ModelUnavailable as error:
            model_available = False
            results.append(replace(fallback, reason=str(error)))
        except InvalidModelOutput as error:
            attempt_status = "invalid-output"
            results.append(replace(fallback, reason=str(error)))
        finally:
            if started is not None and telemetry is not None:
                telemetry.append({"id": email.id, "engine": engine, "status": attempt_status,
                                  "duration_ms": round(max(0, time.monotonic() - started) * 1000, 3)})
    return results


def report(results, engine):
    return {
        "mode": "preview-only",
        "mailbox_connected": False,
        "mailbox_changes": 0,
        "engine_requested": engine,
        "messages": len(results),
        "review_required": sum(row.review_required for row in results),
        "suggestions": [asdict(row) for row in results],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "fixtures/demo.json", help="Local plain-text JSON emails. Defaults to fictional examples.")
    parser.add_argument("--ollama-url", help="Explicit opt-in to inference on a local Ollama server. Never connects to a mailbox.")
    parser.add_argument("--engine", choices=["rules", "ollama", "groq"], help="Default is offline rules unless --ollama-url is supplied")
    parser.add_argument("--model", default=MODEL, help="Installed Ollama chat model; hosted model selection is fixed")
    parser.add_argument("--allow-remote", action="store_true", help="Allow this batch's text to be processed by Groq; requires free-tier confirmation and a local API-key environment variable")
    parser.add_argument("--json", action="store_true", help="Print metadata and label suggestions without subjects or bodies")
    args = parser.parse_args(argv)
    try:
        emails = validate_batch(read_json(args.input))
        results = preview_batch(emails, args.ollama_url, model=args.model, engine=args.engine, allow_remote=args.allow_remote)
    except (ValueError, OSError, UnicodeError, RecursionError):
        # Do not echo raw parser errors, paths, tokens or email text to logs.
        print("Input/configuration rejected. Check the README: input limits, engine, local URL or explicit hosted opt-in and environment variables.", file=sys.stderr)
        return 2
    engine = args.engine or ("ollama" if args.ollama_url else "rules")
    if args.json:
        print(json.dumps(report(results, engine), indent=2))
    else:
        print("NXI EMAIL LABEL PREVIEW | No inbox connected | No mailbox changes")
        print(f"Engine requested: {engine}. Every suggestion requires human review.\n")
        for item in results:
            print(f"{item.message_id}: {', '.join(item.labels)} [{item.method}]")
            print(f"  {item.reason}")
        fallbacks = sum("model" in item.reason.casefold() and item.method not in {"local-model", "hosted-model"} for item in results)
        if fallbacks:
            print(f"\n{fallbacks} message(s) used rule fallback because model inference failed or paused.")
    if engine != "rules" and any(item.method not in {"form-topic", "local-model", "hosted-model"} for item in results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
