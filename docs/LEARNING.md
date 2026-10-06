# Learning notes

What building VART v2 changed in how I work: what v2 changed from the hackathon version and why, and the lessons
recorded in the decisions table of [`PROGRESS.md`](PROGRESS.md).

## What changed from v1, and why
v1 was a one-day hackathon build on a sponsor's confidential documents, with no public demo. v2 uses public
questionnaires and synthetic company packs, takes the visitor's own files, writes answers back into their own
spreadsheet, and gates every claim with an eval in CI. The labels are still decided by code, but the rules now read
document metadata, not file names, so they are not tied to one corpus.

## Lessons
**v1's pinned evidence flattered its numbers.** v1 put the answer key's evidence ahead of the search results, so its
retrieval looked better than it was. v2 never inserts key evidence, and recall is measured against what search
finds.

**Labels are decided by code, not by the model.** The model reads passages and drafts words; quote containment,
negation, scope, conflicts and the draft ceiling are plain rules with unit and property tests. The cost is some
misses a model might have caught; the gain is that every label can be explained from its quote.

**Record and replay, so CI never calls a model.** Every model reply is stored under a key made from the request. CI
replays them with no network and no key, and a changed prompt or model fails because its key is missing. The same
recordings feed the evals, the end-to-end tests and the precomputed sample run.

**Tighten gates from a baseline.** A gate is the larger of the spec's value and the baseline minus 0.02, set after
the first real run, not guessed beforehand.

**Cut NIST outcomes into parts.** An outcome of NIST's Cybersecurity Framework (the US standards body's list of security outcomes) usually asks for several separate things. Asking each as its own
question and combining the answers in code makes each label explainable, and shows which part retrieval or stance
misses (the first gap-check baseline lists every miss with its cause).

**Keep a step's concurrency within the budget's atomic counters.** Answering items at the same time made a run
about 3 times faster: 231 s in 16 steps ($0.06) against about 11 minutes, and it is safe because each budget spend is one atomic statement and no transaction is open
while a model runs.

**Replay the sample run from the recordings the evals score.** The instant demo shows exactly what the evals measured,
and a CI test fails if they ever drift apart.

**Adversary checkpoints before contracts and releases.** A fresh reviewer told to break the design found races,
deadlocks and gaps before code existed (a document delete against a run start, a step writing into a closed run),
which was cheaper than finding them in review of finished code.
