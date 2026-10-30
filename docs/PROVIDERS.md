# Free inference options for NXI

Research checked 30 October 2026. Prices, quotas, model catalogues and terms can change. This is a shortlist to evaluate, not a benchmark winner or an endorsement based on social-media popularity.

## Recommendation

For a low-volume business whose developer will hand over soon, evaluate **Groq Free** first if the company permits external processing of email text. It removes the need to keep a local GPU available. Compare with a small local model on the same examples. **Cloudflare Workers AI Free** is another strong hosted candidate because the site already uses Cloudflare; it has not been integrated here.

If email text must stay on the company's machine, evaluate a local 4B chat model and experimental small decision models. Keep ordinary rules for form topics either way. No automatic replies or destructive mailbox actions are part of this project.

| Candidate | Why consider it | Constraint | Repo status |
| --- | --- | --- | --- |
| Groq Free | Hosted open-weight models, strict JSON schemas, no local GPU | Per-model quotas, external processing, Free plan must remain selected | Optional adapter with explicit opt-in; no real API calls yet |
| Cloudflare Workers AI Free | Existing platform relationship, daily free allowance, hosted chat and decision models | Some models need paid billing; exact model and limits must be checked | Researched only |
| Local Qwen via Ollama | Existing Eye baseline, no hosted inference bill | GPU/CPU memory, power, updates and uptime belong to the operator | Optional adapter with model selection and metadata check |
| Local Tev1 4B / 0.8B | Decision models designed for classification, much smaller options than 9B | Experimental; separate decision API and NXI evaluation needed | Researched only |
| Local Nimble 9B | A Jev-style decision model within the stated parameter limit | Variant, available memory and NXI classification quality still need checking | Researched only |
| Gemini API free tier | Useful for synthetic experiments | Free-tier content can be used to improve Google's products | Not selected for company email |
| Cerebras | Fast hosted inference to compare experimentally | Current pricing describes a one-time promotional credit; older free-tier guides are stale | Not a dependable ongoing-free choice |
| Jev | Purpose-built typed decisions | Usage-based paid service, outside the no-paid-dependency requirement | Not used |

## Verified details

### Groq

[Billing documentation](https://console.groq.com/docs/billing-faqs) distinguishes Free from the paid Developer tier. [Limits](https://console.groq.com/docs/rate-limits) apply by organisation and model, with several simultaneous token/request limits; the account console is authoritative. Older Llama-based templates may no longer match the current catalogue. The adapter uses a model listed for [strict structured outputs](https://console.groq.com/docs/structured-outputs).

[Data handling](https://console.groq.com/docs/your-data) says inference content is not retained by default except for specified cases, and offers zero data retention controls to all customers. Metadata is still retained. [Groq's trust FAQ](https://trust.groq.com/faq) says it does not train its models on customer inputs and outputs. This is still external processing, not local inference. No guarantees about perpetual free capacity or uptime are made here.

### Cloudflare

[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) gives a 10,000-neuron daily free allowance. On Workers Free, exceeding the allowance fails rather than buying extra capacity. Some frontier models require paid billing, so select a Free-eligible model. [Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/) is a hosted decision model worth comparing for this task. [Data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/) states no model training on customer content and describes standard-inference retention limits and exceptions. Logging, caching and other stateful features can retain content separately.

### Local decision models and memory

[Ollama's September 2026 announcement](https://ollama.com/blog/ollama-now-supports-jev-style-decision-models) introduces the `/v1/systemone` endpoint and Nimble, Tev1 4B and Tev1 0.8B. That is a free way to explore Jev-style decision interfaces without using the hosted Jev service. These are separate models, not a local copy of Jev, and reported public benchmarks do not establish NXI email accuracy.

The user clarified that the local ceiling is approximately **9B parameters**, not 9 GB of memory. [Nimble](https://ollama.com/library/nimble) is a 9B candidate; [Tev1](https://ollama.com/library/tev1) has smaller 4B and 0.8B variants. Compare these with the existing local chat model before choosing. A larger model is not automatically a better classifier. Parameter count alone also does not establish runtime fit: quantisation, context/KV cache, concurrent requests and available memory still matter. Hosted inference is not constrained by the local 9B limit.

No model was downloaded, upgraded or run on Eye. The current local adapter calls the chat endpoint; a decision adapter still needs implementation and testing. It must not silently route decision models through a chat endpoint.

### Options excluded from the zero-paid baseline

[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) distinguishes free and paid data-use terms; free-tier content can be used to improve products. Use fictional inputs for comparison, not private family or customer correspondence.

[Cerebras's current pricing](https://www.cerebras.ai/pricing) describes a one-time $5 promotional credit requiring a payment method and expiring after 30 days. That differs from older indexed documentation describing an ongoing free tier.

[TypeSafe's pricing page](https://typesafe.ai/) advertises usage-based Jev pricing. It could be inexpensive at small volumes, but it is not the zero-paid dependency requested here. We did not create an account, buy credits or call Jev.

## What practitioners are actually building

- [Labelr's author on Reddit](https://www.reddit.com/r/developersIndia/comments/1rh2v9h/i_built_an_opensource_cli_tool_that_autolabels/) and [repository](https://github.com/Pankaj3112/labelr): one Gmail application with local and hosted provider choices. Useful architecture reference. The author's claims are not our security or accuracy audit.
- [Job Inbox Guardian on LinkedIn](https://www.linkedin.com/posts/mohammed-dabbah-a79416311_localai-llm-rag-activity-7487901963108528128-nyLz): its builder emphasises deterministic rules, validated model output and manual review. It also sends notifications and marks mail read, which NXI explicitly does not want. Those actions were not adopted.
- [A Groq/Gmail label workflow](https://n8n.io/workflows/17365-label-gmail-emails-by-priority-with-groq-llama-33/): a concrete hosted classification example. Its model names, OAuth permissions and free limits need current verification; it is not installed here.
- [Distil Labs' local classifier](https://github.com/distil-labs/distil-n8n-gmail-automation): shows a small specialised model can be useful, but its fixed generic labels are not NXI's label set. Its reported benchmark is not directly transferable.

X was searched as requested, but no sufficiently relevant direct post was verified. Official API, pricing and data-use documentation underpins the technical conclusions. Social posts help find implementation patterns, not establish pricing or safety.

## Selection test

Use a separate, authorised set of 50 to 100 human-labelled NXI examples. Keep personal content local unless the chosen external processor has been approved. Compare full-label agreement, missed support/refund requests, false spam suggestions, invalid responses, throttling, latency and the share requiring manual review. Freeze the evaluation set before tuning prompts. Do not translate a model's confidence score into a correctness percentage without measuring calibration.

Choose the smallest operational setup that meets those measurements. A model API does not host the inbox polling code. A small scheduled worker can later run independently of Eye, but mailbox authorisation, scheduling and deployment are future work. Mail must still arrive normally if classification is unavailable.
