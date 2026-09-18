---
name: df-mlops
description: DeltaForce MLOps practices on Databricks — the ML operations strategy in the Architecture, realistic data samples and splits without leakage, baselines, model challenges and leaderboards, champion and challenger aliases in Unity Catalog, validation before promotion, serving, monitoring and retraining, and Hugging Face models trained and served on Databricks. Use when designing, building or testing an ML feature.
user-invocable: false
---

# DeltaForce MLOps

The Data Scientist owns the modelling and the ML pipeline code; the Solution Architect owns the strategy in the Architecture and designs it with the Data Scientist; the DevOps Engineer deploys; the QA Engineer verifies on their own. For current APIs load `databricks-ml-training`, `databricks-model-serving` and `databricks-execution-compute`.

## 1. Strategy — Architecture section *ML operations*

Decided before G1, one subsection per model:

| Topic | Decide and write down |
| --- | --- |
| Problem | Task (classification, regression, forecasting, ranking, …), target, prediction grain and horizon, who uses a prediction and how, the business metric it moves |
| Metrics | Primary model metric that stands for the business metric, secondary metrics (calibration, latency, cost), the threshold and the baseline to beat — from the acceptance criteria |
| Data | Sources, feature tables (point-in-time correct for temporal data) in the schema the Architecture assigns to ML objects — gold unless the design says otherwise —, label definition and delay, sampling and split strategy |
| Candidates | Baseline, model families to challenge (classical, gradient boosting, deep learning, Hugging Face pre-trained or fine-tuned, foundation models through `ai_query`), tuning budget |
| Promotion | Deploy code, not models: the same training and validation code runs in every environment of the conventions; the model registered in Unity Catalog in the schema the Architecture assigns, named from bundle variables; `challenger` and `champion` aliases and the validation that moves them |
| Serving | Batch inference job writing a predictions table in the schema the Architecture assigns, or a model serving endpoint declared in the bundle; CPU or GPU, within what the workspace allows (`discovery.md`) |
| Monitoring | Inference tables or a predictions table, data quality monitoring of features and predictions (drift), alerts, how labels come back |
| Retraining | Schedule or trigger (drift, metric drop, new data), the job that retrains, who approves promotion outside dev |
| Reproducibility and cost | Seeds, data versions, pinned libraries, compute choice |

Record expensive choices (model family, serving mode, GPU) as ADRs.

**Every experiment lives in MLflow.** Exploration, training, tuning and evaluation are MLflow runs in the project's experiment, declared in the bundle: parameters, metrics, data version, the model and its signature, artifacts. A number that is not in an MLflow run does not exist — never report a metric from a notebook cell, a log or a printed output, and never compare candidates outside a challenge (§5). Registered models and their versions carry a description, like every other object (`df-engineering-standards`).

## 2. Realistic data

- Develop and test on the real data in the dev catalog: sample it, do not invent it. Synthetic data (`databricks-synthetic-data-gen`) only for rare edge cases and transformation tests, labelled as synthetic.
- Production data only when the conventions or the kickoff request allow it, read with the production tools and never copied without PO approval (`df-engineering-standards`).
- Make the sample look like the population: stratify by target and key segments, keep rare classes, use a time window for temporal data. Compare the distribution of the target and of the key features with the full table and report it.
- Record source tables, Delta version or timestamp, filters and the sampling query in the MLflow run, so the dataset can be rebuilt.

## 3. Splits without leakage

- Train, validation and test. Tune on validation, or with cross-validation on small data; use the test set once, for the final comparison.
- Temporal data: split by time — train on the past, test on the future — never at random. Entities with many rows (customer, device): group split, so an entity is never on both sides.
- No feature computed after the prediction time or derived from the target, no duplicates across splits; scalers and encoders fitted on train only, inside the model pipeline.
- Fixed seeds; save the split (ids or a split column) and log it.
- **Features must be as of prediction time.** A feature table that keeps only the current value leaks the future into training: give feature tables an effective timestamp and read them with a point-in-time join (as-of join on the entity and the event time), or rebuild the feature from the events available before the prediction. Say in the report which features are point-in-time and which are static by nature.

## 4. Baseline first

Before any real model, log a baseline on the same split and metrics: majority class or mean, last value or seasonal naive for forecasts, the rule the business uses today, or a linear model. Every candidate is compared with it. The model approved at G2 becomes the project baseline: a later change must beat it on the same test set version.

## 5. Model challenge

- Same data, split, features and metrics for every candidate: one MLflow parent run for the challenge, one child run per candidate with parameters, metrics, data version, training time and model size.
- Challenge different families, not variants of one — for example a linear model, gradient boosting, a Hugging Face model when the input is text, images or audio, a foundation model with `ai_query` for zero- or few-shot.
- Tune the finalists within a declared budget (for example Optuna, trials as child runs).
- Choose on the primary metric on validation, then compare the finalists on test with confidence intervals (bootstrap). A difference inside the interval is a tie: prefer the simpler, cheaper, more explainable model.
- Error analysis of the champion: metrics per segment, worst errors, calibration for classifiers, feature importance or SHAP.
- Leaderboard for the report:

| Candidate | Family | Validation metric | Test metric (95% CI) | Latency | Size or cost | Notes |
| --- | --- | --- | --- | --- | --- | --- |

## 6. Registration and promotion

- Log the model with signature and input example, register the chosen version in Unity Catalog and set `challenger` on it.
- A validation step — a job task, the same code in every environment — compares `challenger` with `champion` on the same test data and moves `champion` only when the challenger wins and meets the thresholds. On dev it runs in the team's jobs; elsewhere through CI/CD.
- Batch inference and serving load the model by alias (`models:/<catalog>.<schema>.<model>@champion`, names from bundle variables), never by version number.

## 7. Serving, monitoring, retraining

- Serving endpoints, jobs and monitors are bundle resources, deployed by the DevOps Engineer.
- Log predictions: inference tables on serving endpoints (payload logging — the endpoint writes requests and responses to a Unity Catalog table), a predictions table for batch. Both carry the model name and version so a number can always be traced back to what produced it.
- Monitor what can move: input drift on the features that matter, drift of the prediction distribution, and — when labels arrive — the model metric against the value approved at G2. Thresholds come from the Architecture; a monitor is a bundle resource like any other, and what it should do when it fires (open a bug, retrain, warn) is decided at design time, not when it fires.
- Retraining is a bundle job: it registers a new `challenger` and runs the same validation.

## 8. Hugging Face models on Databricks

The Hugging Face skills listed in your agent hold model, dataset and training know-how. On a DeltaForce project apply it on Databricks:

- **Choose** with `huggingface-best` and `hf-mem` (memory for the compute available). Check that the licence allows the client's use and whether the model is gated; record the model id and revision.
- **Load** in code that runs on Databricks (`transformers`, `sentence-transformers`), pinning the revision; cache weights in a volume of the dev catalog when they are downloaded repeatedly.
- **Fine-tune** with the recipes of `trl-training`, `huggingface-llm-trainer`, `huggingface-vision-trainer` or `train-sentence-transformers` (LoRA or full fine-tuning, losses, hyperparameters), running on Databricks GPU compute from a bundle job. Save checkpoints to a volume, log the run and the model with MLflow, register it in Unity Catalog.
- **Serve** from Unity Catalog on a model serving endpoint, alone or combined with other models — a pyfunc or an agent that calls a Hugging Face model and a foundation model.
- **Never** push models, datasets or checkpoints to the Hugging Face Hub, run Hugging Face Jobs, or create Spaces or Inference Endpoints: models, data and training stay on Databricks. The guardrails block `hf upload`, `hf jobs` and an enabled `push_to_hub`. Where a Hugging Face skill says to push to the Hub or use Jobs, use the Databricks way above.
- A Hugging Face token, for gated models, lives in a Databricks secret scope declared in the bundle; a person sets its value. Never write it in code, files or commands.

## 9. Evidence for G2

- `tests/evaluation/` checks the thresholds of the acceptance criteria on the registered version, loaded by alias.
- The QA Engineer recomputes the metrics from the model and the saved test split — never from the numbers the Data Scientist logged — and checks the split for leakage.
- The report adds: problem and metric, data sample and split with versions, baseline, leaderboard, champion version and alias, error analysis, what monitoring and retraining are in place, limitations.
