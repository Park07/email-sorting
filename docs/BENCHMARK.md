# Run the fictional-email comparison

No inbox is needed. Run from the repository root with Python 3.10+. No pip installs. All 24 bundled cases are fictional development examples, not an independently held-out accuracy benchmark.

The workspace that prepared this code could not reach Groq's API and had no local model runtime. A model-list connectivity attempt failed before inference. No live model score is claimed. Run the commands below on your own machine with network access.

## 1. Offline baseline

**CHANGES SOMETHING.** Creates `results/rules.json` and its parent directory if needed. No network. Existing reports are never overwritten. Undo: remove only this report if you no longer need it.

```sh
python3 -B evaluate.py --output results/rules.json
```

The expected baseline is 20 exact matches out of 24. Rules have known failures with negation, indirect wording and non-English text. This does not establish real inbox accuracy.

## 2. Hosted Groq run

Use your own Groq account confirmed to be on **Free**. Create or rotate the API key in the provider console and enter it only at the hidden terminal prompt. Do not paste it into chat, shell history or a repository. The acknowledgement below does not query or verify account billing. An upgraded account could incur charges; keep it on Free for this experiment.

**CHANGES SOMETHING.** Sends fictional examples to Groq, consumes the account's quota and saves `results/groq.json`. The key exists only in process memory, and is not written to the report. Undo: Ctrl+C stops further work; requests already sent cannot be recalled. Remove the report if unwanted. Existing reports are not overwritten. No mailbox is contacted.

```sh
python3 -B evaluate.py --engine groq --allow-remote --confirm-free-tier --prompt-key --output results/groq.json
```

Allow several minutes. Request starts are spaced by at least 10 seconds to reduce bursts. This is not a quota guarantee: account limits and token budgets vary. A 429 or connection failure pauses the remaining requests without retrying, changing provider or enabling paid capacity. The report is marked incomplete and exits with code 3. After resolving the issue, use a new output filename for another run.

## 3. Optional local comparison

Run on the machine that already hosts the authorised Ollama chat model. Use the **same repository revision**. Do not attempt to reach the private office network from this workspace. The user runs Eye commands themselves. The local target is roughly 9B parameters or smaller; select an actual installed model, not a guessed model tag. This does not download or modify any model.

**READ-ONLY.** Lists installed models on that machine.

```sh
ollama list
```

**CHANGES SOMETHING.** Runs local inference and may load a model into shared GPU/CPU memory; creates `results/local.json`. Replace `YOUR_INSTALLED_CHAT_MODEL` with the exact installed chat-model name. Undo: Ctrl+C stops further requests; already running compute may complete. Remove the report if unwanted. Do not stop other people's workloads.

```sh
python3 -B evaluate.py --engine ollama --ollama-url http://127.0.0.1:11434 --model YOUR_INSTALLED_CHAT_MODEL --output results/local.json
```

Nimble and Tev1 use a separate decision API. They remain research candidates and are not compatible with this chat adapter.

## 4. Read the comparison

Copy only the local report to the same `results/` folder if the local run happened on another machine. Reports contain opaque case IDs, labels, timing and fingerprints, not email text or keys.

**READ-ONLY.** Prints the hosted-versus-rules comparison as a Markdown table. No network or file writes.

```sh
python3 -B compare.py results/rules.json results/groq.json
```

**READ-ONLY.** Adds the optional local report, after it exists.

```sh
python3 -B compare.py results/rules.json results/groq.json results/local.json
```

Reports must match the fixture, prompt, classifier and evaluator fingerprints. If code or examples change, rerun the baseline too. Incomplete inference is shown as incomplete, never ranked using fallback-rule accuracy. The comparison can be copied back for review; do not include keys or original emails.

## What the numbers mean

- Exact agreement requires every expected category and no extra category.
- Missed support/refund labels identify important requests the classifier overlooked.
- False spam labels count legitimate examples wrongly suggested as spam. Nothing moves to Spam.
- Median and p95 measure successful, validated model responses, including HTTP time. They exclude deliberate pacing and the local metadata check. p95 uses nearest-rank on a small sample, not a production service-level claim.
- Total time includes pacing, setup and failures. No model calls means no model latency score.
- Model runs keep form-topic rules, so the result describes the combined classifier, not the model alone. All messages still require human review.

After this smoke comparison, evaluate an authorised, independently labelled NXI sample before choosing a model for actual mail. Keep real examples and results out of this public repository.
