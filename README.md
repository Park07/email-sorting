# NXI email sorting

Review-only email classification for NX Intelligence. Python 3.10+, standard library only, with no required paid service.

**Status:** working local-file preview. No inbox is connected. No messages have been read from a live mailbox or labelled. Model integrations have mocked contract tests; real model quality has not been measured yet.

The application only proposes labels. It has no code to send, reply, forward, delete, archive, move messages, change read status or apply mailbox labels. All suggestions require human review.

## Try it in one minute

Python and Git must already be installed. No pip packages are needed.

**CHANGES SOMETHING.** Creates a new checkout. Undo: remove only this new checkout after preserving any wanted work. If the directory already exists, inspect it instead of overwriting it.

```sh
git clone https://github.com/Park07/email-sorting.git
```

**READ-ONLY.** Selects the checkout and classifies eight fictional messages. No network, model, credentials or output files.

```sh
cd email-sorting
python3 -B classifier.py
```

**READ-ONLY.** Prints the same preview as JSON, including opaque IDs and labels, without email subjects or bodies.

```sh
python3 -B classifier.py --json
```

## Choose where classification runs

| Engine | Implemented | Cost and data flow |
| --- | --- | --- |
| `rules` | Default | No network or AI charge. Topic and keyword hints only. |
| `ollama` | Optional local chat adapter | Uses an existing installed model. No hosted inference charge; the machine, power and maintenance remain your responsibility. |
| `groq` | Optional hosted adapter | Can use Groq's Free plan. Requires explicit remote opt-in, a local API key and confirmation of the account's Free plan. The selected email text goes to Groq. |

No inference adapter is automatically enabled. A present API key does not select hosted inference. There is no fallback to a paid service, and no provider switch on failure.

Read [setup instructions](docs/SETUP.md) for local or hosted inference. Read [provider research and recommendation](docs/PROVIDERS.md) for Cloudflare, Groq, local decision models and the user's approximate 9B-parameter local model limit.

## Suggested labels

| Label | Examples |
| --- | --- |
| Workshops | Ages, dates, participation and workshop enquiries |
| Schools and quotes | School visits, classes, group arrangements and bulk pricing |
| Products and engineering | SoraDrive, sensor bars, specifications and engineering |
| Orders and delivery | Existing orders, shipping, tracking, back-orders and ETAs |
| Support and refunds | Faults, cancellations, returns and duplicate charges |
| Suppliers and invoices | Supplier correspondence, purchase orders and invoices |
| Suspected spam | Review only; never the mailbox's Spam folder |
| Needs review | Added to every v1 suggestion |

Labels are prefixed with `NXI/`. Several can apply to one email. An enquiry does not become a confirmed booking, and an email is not proof of payment.

## Checks and evaluation

**READ-ONLY.** Runs focused tests with mocked HTTP. Temporary test files are automatically cleaned. No live model, mailbox or paid API is contacted.

```sh
python3 -B -m unittest discover -s tests -v
```

**READ-ONLY.** Evaluates the rules against 24 authored fictional cases and prints per-category precision, recall, missed labels and mismatched IDs.

```sh
python3 -B evaluate.py
```

The rule baseline matches the full expected category set on 20/24 examples. This **is not production accuracy**: the examples are synthetic and authored alongside the implementation. Known failures include negation, indirect wording, a non-English message and legitimate text discussing a scam. No score for a real model is claimed. See [evaluation and architecture notes](docs/ARCHITECTURE.md).

## Input and privacy

Local JSON files contain an array of objects with exactly `id`, `subject` and `body`. The body must be plain text. Use opaque IDs. Maximum 100 messages, 2 MB per file, 1,000 UTF-8 bytes per subject and 8,000 per body. MIME, HTML and attachments are not supported. Links are never fetched.

Keep real examples and local results in the ignored `private/` and `results/` directories on your own machine. Do not put mail, credentials, model outputs or internal infrastructure details in this public repository or its issues. Git ignore rules are not encryption or a substitute for checking commits.

Reports omit email subjects, bodies, API keys and raw model output. Local inference first checks installed-model metadata and refuses advertised cloud aliases. A timeout, quota error or invalid response preserves a visible rule preview for review. Exit code 0 means processing completed, not that labels are correct; 2 means invalid configuration/input; 3 means requested inference was not completed for every relevant message.

## Inbox connection comes next

Ask which provider hosts the intended NXI inbox, its address and who can authorise access. No passwords are needed in chat. Start with read-only preview access. Applying labels later requires a separately reviewed provider adapter. Standard Gmail label application normally needs broader `gmail.modify` permission; it is not a permission-level label-only guarantee.

This project is independent of the public website and student-facing robot chat. Neither should receive staff email data. Future inbox delivery must remain independent of classification availability.
