# Architecture and boundaries

## Current processing

1. Load a bounded local JSON batch with opaque IDs, subjects and plain-text bodies.
2. Validate shape, encoding limits and unique IDs before processing.
3. Produce deterministic topic/keyword hints. Website topic prefixes are hints, not sender authentication.
4. Optionally select one model backend explicitly: local Ollama chat or hosted Groq. Known form topics can skip inference. Other messages receive the same bounded task and fixed category list.
5. Validate complete model output against the application policy. Unknown fields, system mailbox labels, malformed JSON, truncation and action/tool requests are rejected.
6. Print human-review suggestions and metadata only. Every result requires review. Nothing calls an email provider.

The model suggests categories. Application code controls which labels are possible and forces review. Provider responses never become arbitrary function calls. Classification and mailbox integration are separate concerns; selecting a different model does not grant mailbox capabilities.

## Failure handling

No automatic retries or provider switching run in this preview. A connection/rate-limit failure pauses further inference in the batch, retains all remaining messages as visible rule previews and returns exit code 3. Invalid individual outputs also retain the fallback with a reason. The operator still has the original input file and can rerun later. There is no persistent queue yet, so this does not claim crash recovery or exactly-once mailbox processing.

Both transports block redirect following and environment proxies. The hosted endpoint is fixed and HTTPS. Local metadata is checked before sending message text. Authentication and HTTP errors are sanitised so raw provider responses, tokens and email bodies do not appear in reports.

## Actual tests versus model evaluation

The unit suite checks output restrictions, remote opt-in, free-account acknowledgement, malformed credentials, schema violations, throttling, partial failures, metadata checks, bounded payloads and privacy of reports. All HTTP responses are mocked. CI runs the offline fixture and rules evaluator on Python 3.10 and 3.12; it needs no secrets.

The evaluator reports TP/FP/FN, precision, recall and full-label exact matches. Missing denominators produce null. It reports local and hosted classifications separately and fingerprints fixtures, code and prompt. Its exit status is a transport/configuration result, not an accuracy gate. The bundled 24 cases are development examples, not an independently held-out benchmark. Some deliberately expose current keyword limitations.

Remaining evaluation work includes measured model latency, model/version pinning, output correctness on independent cases, hardware memory under the intended context size and the operator's ability to recover without developer help. No live backend has been evaluated from this workspace.

## Before inbox integration

Confirm the actual provider, intended mailbox and who can authorise it. Initially request read-only access and retain manual review. Do not assume the connected personal account is the company inbox. Use the provider's maintained OAuth client when adding authentication. Never put credentials in this repository or ask for them in chat.

If label application is later enabled, its adapter must accept only allowlisted NXI user labels and only add labels. It needs no send, draft, forwarding, trash, delete, archive, move or read-status implementation. Preserve existing labels and corrections, handle provider retries idempotently and record only minimal label-operation metadata. Delivery must not depend on this worker.

Provider permission scope can be broader than the code's actions. Standard Gmail `gmail.labels` handles label definitions; applying labels to messages normally needs `gmail.modify`, which grants broader capabilities. That permission has not been requested. If the account owner rejects broad permissions, keep read-only suggestions and manual label application. Check the actual provider rather than promising a label-only OAuth scope.

## Cost boundary

There are no required paid dependencies. Offline mode makes no network calls. Local mode consumes existing machine resources. Hosted mode can use a free account, but this application cannot independently verify billing state; the confirmation flag is not a spending-control API. Keep the provider account on Free and do not enable paid fallback. Recheck terms and quotas before operating. Exceeding free limits should lead to review, not an upgrade.

## Repository boundary

This repository contains code, prompts, fictional fixtures and public documentation only. Real mail, keys, private results and infrastructure details belong in operator-controlled storage. The website and public student chat remain separate. No deployment, background service, inbox session or new external account was created by importing this project.
