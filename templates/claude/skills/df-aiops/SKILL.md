---
name: df-aiops
description: DeltaForce AIOps practices for GenAI on Databricks — the AI operations strategy in the Architecture, realistic evaluation datasets, baselines and challenges between models, retrieval and prompt designs, MLflow evaluation, tracing and prompt versions, serving and AI Gateway, monitoring, Hugging Face models on Databricks and Agent Bricks. Use when designing, building or testing a GenAI feature.
user-invocable: false
---

# DeltaForce AIOps

The AI Engineer builds the GenAI solution and its operations; the Solution Architect owns the strategy in the Architecture and designs it with the AI Engineer; the DevOps Engineer deploys; the QA Engineer verifies on their own. For current APIs load `databricks-mlflow-evaluation`, `databricks-model-serving`, `databricks-vector-search`, `databricks-ai-functions` and `databricks-agent-bricks`.

## 1. Strategy — Architecture section *AI operations*

Decided before G1:

| Topic | Decide and write down |
| --- | --- |
| Pattern | The simplest that meets the criteria: AI functions in batch SQL, RAG, a tool-calling agent, Agent Bricks, a fine-tuned model |
| Quality | What a good answer is (correctness, groundedness, relevance, safety, format), the judges and the thresholds — from the acceptance criteria — plus latency and cost per request |
| Models | Candidate LLMs, embedding and reranking models: foundation models, external models through AI Gateway, Hugging Face models served on Databricks; chosen by challenge |
| Retrieval | Sources, parsing and chunking, metadata and filters, embedding model, vector index and how it stays in sync |
| Prompts and code | Prompts versioned in the MLflow Prompt Registry with aliases; agent code logged as an MLflow model and registered in Unity Catalog |
| Promotion | Deploy code: the same evaluation runs in every environment of the conventions; aliases for prompts and models |
| Serving | Model serving endpoint or Databricks App declared in the bundle; AI Gateway rate limits, guardrails, usage and inference tables |
| Monitoring | MLflow tracing in production, judges on sampled traces, user feedback, cost and latency alerts |
| Risks | Hallucination, prompt injection, sensitive data, what the agent may access — and the mitigations |

Record expensive choices (pattern, model provider, vector index design) as ADRs.

**Every experiment lives in MLflow.** Each candidate — LLM, embeddings, chunking, retrieval, prompt variant — is an MLflow evaluation run in the project's experiment, with the prompt version, the dataset version and the judge results; tracing is on. A quality number that is not in an MLflow run does not exist. Indexes, endpoints, evaluation tables, registered agents and prompts carry a description, like every other object (`df-engineering-standards`).

## 2. Realistic evaluation data

- Build the evaluation dataset from the real documents and data in the dev catalog: questions a user would ask, with expected answers or expected facts and sources. Include hard, ambiguous, out-of-scope and adversarial (prompt injection) cases.
- Synthetic questions may widen coverage: label them and review a sample. When answers need domain knowledge, the PO or a business user confirms a sample at G1 or G2.
- Store it in gold as a versioned table; keep a held-out part that is never used while tuning prompts.
- Production data or traces only when the conventions or the kickoff request allow it.

## 3. Baseline and challenge

- Baseline: the simplest setup — one prompt with a mid-size foundation model, `ai_query` zero-shot, keyword search for retrieval.
- Change one dimension at a time on the same evaluation set: LLM, embedding model, chunking, retrieval depth and reranking, prompt variants, a Hugging Face or fine-tuned model. Each candidate is an MLflow evaluation run.
- Leaderboard for the report:

| Candidate | What changed | Quality scores | Thresholds met | Latency p50 / p95 | Cost per 1,000 requests | Notes |
| --- | --- | --- | --- | --- | --- | --- |

- Choose on the thresholds first, then cost and latency; a tie goes to the simpler setup. The setup approved at G2 is the baseline a later change must not fall below.

## 4. Evaluation

- MLflow GenAI evaluation with built-in judges, guideline judges written from the business rules, and deterministic checks (format, citations present, refusal out of scope).
- Evaluate retrieval (are the expected sources found) separately from generation.
- Check the judges against a small human-labelled sample before trusting them.
- `tests/evaluation/` runs the evaluation on the deployed endpoint or the registered version against the thresholds; the QA Engineer runs it independently.
- **Keep a red-team slice in the evaluation set**: prompt injection through the retrieved documents ("ignore your instructions"), questions outside the scope, requests for data the user may not see, and the personal or sensitive data the domain can produce. The expected answer is the refusal or the safe answer, and it is scored like any other case — a release that regresses on this slice does not ship.

## 5. Build and operate

- Tracing on from the first prototype; prompts loaded from the registry by alias; model, index and endpoint names from bundle variables.
- Vector search endpoints and indexes, serving endpoints, apps and monitors are bundle resources, deployed by the DevOps Engineer.
- Respect the workspace limits recorded in `discovery.md` (vector search endpoints, GPU serving, Agent Bricks availability, foundation models available).
- **Guardrails belong to the endpoint, not to the prompt**: where the workspace offers AI Gateway on the serving endpoint, configure there what must hold whoever calls it — safety filters, blocked topics, personal data handling, rate limits and the usage tracking that shows what it costs. A prompt asking the model to behave is not a control; the gateway is. Record in the Architecture what is enforced at the gateway and what is left to the prompt.

## 6. Hugging Face models

Embedding models, rerankers, classifiers and small generative models from Hugging Face run on Databricks: choose with `huggingface-best` and `hf-mem`, check licence and gating, fine-tune with `train-sentence-transformers` or `trl-training` on Databricks GPU compute from a bundle job, log and register with MLflow in Unity Catalog, serve on a model serving endpoint alone or together with foundation models. Never push to the Hugging Face Hub, run Hugging Face Jobs or create Spaces or Inference Endpoints — the guardrails block it; a token for gated models lives in a Databricks secret scope whose value a person sets.

## 7. Agent Bricks

Knowledge Assistants and Supervisor Agents cannot be declared in the asset bundle:

- Check in `discovery.md` that the workspace supports them.
- The AI Engineer creates and updates them on dev with `manage_ka` and `manage_mas` (`create_or_update`), with sources in volumes and functions of the dev catalog. Reads (`get`, `find_by_name`) are open to every role; deleting one needs a person.
- Keep each definition in `src/ai/agent_bricks/<name>.yml` — name, description, instructions, knowledge sources or sub-agents, examples — so it can be recreated.
- List them under *Created outside the bundle* in the report, with how other environments get them: CI/CD cannot promote them.
- Evaluate them like any other agent.

## 8. Evidence for G2

The report adds: pattern and models, evaluation dataset version, baseline, leaderboard, thresholds met, evaluation and trace run ids, cost and latency, Agent Bricks created outside the bundle, known failure modes.
