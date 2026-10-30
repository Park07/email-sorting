# Optional inference setup

The default preview needs only Python 3.10+. Run every command from the repository root unless stated otherwise. All bundled messages are fictional.

## Local model on your own machine or Eye

You run the Eye side yourself. No office address or login details are included here. Copy a fresh clone to your approved machine using your existing access. Do not copy private examples into a public repository.

Ollama must already be installed and running, and the chat model must already be downloaded. The application does not install software, pull models, create aliases, unload workloads or change server configuration. The initial model is `qwen3.5:4b`; it is a baseline, not a claim of best accuracy.

**READ-ONLY, on the machine running Ollama.** Checks installed models without inference. Substitute the operator-confirmed Ollama host in your own environment if it is not the default loopback service.

```sh
ollama list
```

**CHANGES SOMETHING.** Runs inference on fictional messages through your local Ollama daemon. May load a model and use shared CPU/GPU memory. Writes no report and changes no mailbox. Undo: Ctrl+C stops the client; an already accepted generation may finish. Completed compute cannot be undone. Do not stop other people's workloads.

```sh
python3 -B classifier.py --engine ollama --ollama-url http://127.0.0.1:11434
```

**CHANGES SOMETHING.** Same shared-compute effects and undo as above, using another installed chat model. This is an example model name to replace with one you have already installed.

```sh
python3 -B classifier.py --engine ollama --ollama-url http://127.0.0.1:11434 --model YOUR_INSTALLED_CHAT_MODEL
```

**CHANGES SOMETHING.** Evaluates fictional cases with the local model and prints metrics. Same compute effects and undo as above. No live inbox or persistent report.

```sh
python3 -B evaluate.py --engine ollama --ollama-url http://127.0.0.1:11434
```

Only literal loopback/RFC1918 endpoints or `localhost` are accepted. Credentials, URL paths, query strings, fragments, proxies and redirects are refused. Before sending any email text, the adapter reads `/api/tags`, checks that the selected model exists in local GGUF form and rejects advertised remote-model aliases. This assumes the daemon is trusted and models are not changed concurrently. It cannot independently prove what a modified daemon does internally.

Nimble and Tev1 are decision-model candidates, not drop-in chat-model names for this adapter. They use `/v1/systemone`, which is not implemented here yet. Do not pass them to the chat adapter. Do not upgrade Eye or download models without agreeing the change with its operator.

## Hosted model through Groq's Free plan

Ollama and a GPU are not needed for this mode. The small Python program still runs on a machine; a hosted model API does not itself connect to the inbox or schedule the program.

1. Use an account that is confirmed to be on Groq's **Free** plan. Do not upgrade to Developer, add paid capacity or enable paid alternatives for this zero-budget experiment.
2. Create an API key in your own provider account. Never put it in chat, source code, a GitHub issue or a shell command containing its literal value.
3. Review the provider's data controls. Groq documents a zero data retention option for all customers. For actual company mail, the company must authorise sending message text to that external processor. Start with fictional fixtures.
4. The initial hosted model is `openai/gpt-oss-20b` with strict structured output. It is served by Groq; it does not use an OpenAI API account or subscription. Confirm model access and current free quotas in the account console.

**CHANGES SOMETHING.** Prompts privately for a key, holds it only in this Python process, and sends the bundled fictional examples to Groq. Consumes the account's free quota. The confirmation variable is an operator acknowledgement, not a server-side verification of billing status. If you use an upgraded account, the provider could charge despite this flag. Undo: Ctrl+C stops the client; already transmitted requests and consumed quota cannot be undone. The process environment disappears on exit. This command writes no files or mailbox state.

```sh
python3 -B - <<'PY'
import getpass
import os
import classifier

os.environ['GROQ_API_KEY'] = getpass.getpass('Groq API key, hidden: ')
os.environ['NXI_GROQ_FREE_TIER_CONFIRMED'] = 'yes'
raise SystemExit(classifier.main(['--engine', 'groq', '--allow-remote']))
PY
```

For evaluation, use [the single-command benchmark setup](BENCHMARK.md), which adds pacing, response timings and saved comparison reports. The 24-case run can still encounter free-tier rate limits. It reports that failure rather than claiming a successful model benchmark.

If your existing process manager already provides the key and confirmation environment variables securely, use the following command.

**CHANGES SOMETHING.** Sends fictional messages to Groq using the already configured environment. Same quota/transmission effects and undo as above. Does not save or display the key.

```sh
python3 -B classifier.py --engine groq --allow-remote
```

The API destination is fixed to Groq's HTTPS endpoint. There are no tools, searches, uploads or mailbox credentials in the model request. Redirects and environment proxies are disabled. On throttling or service failure, remaining messages retain rule suggestions for review; no other provider is silently tried and no paid capacity is enabled. Real input can be supplied with `--input private/emails.json` only after its external processing is authorised.

## What is not connected

No mailbox API, OAuth session, scheduler, database, server deployment or real provider account has been connected by this implementation. The remote and local adapters have been tested with mocked responses only. The code cannot send or remove email, and there is no toggle that enables those actions.
