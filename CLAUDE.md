# Project context — agentic-llm-redteam

## What this is

A multi-agent system that automates the red teaming of LLM applications: you give it
an endpoint, you get back a list of validated vulnerabilities (prompt injection,
jailbreak, system prompt leakage…), following the OWASP Top 10 for LLM Applications.

A personal learning project **and** a public showcase (public repository, read by
recruiters). Both goals count: the code must be clean and readable, and the README must
stay honest about how far it has got.

## Current state: 14 phases closed, 2 and 5 in progress

**This section describes NOW, so it rots.** It is kept to a screen on purpose:
an addition here should DISPLACE something, not accumulate. The narrative of
how each figure came about is in the journal, where it is dated and does not
rot. The roadmap table says which phases are closed; the architecture map says
what each file does; neither is repeated here.

The full campaign **reconnaissance → planning → attack → judgement → replay**
runs end to end locally, the next attempt is chosen from what the target has
already replied (phase 3a), and a campaign can attack over SEVERAL TURNS
(`--multiturn`, phase 3b) or PLANT each payload in retrieved content and then
ask one fixed innocuous question (`--indirect`). It reaches an endpoint by a
JSON POST, a GET, a `multipart` form or a WebSocket (`--target-transport`).

THREE vulnerable targets ship with it, one per ASSET: `demo` a secret string,
`records` access control over look-alike records, `docs` the integrity of its
own instructions against content it retrieved.

| | figure | guarded? |
|---|---|---|
| source payloads | **1,166** (1,143 garak / 52 probes, 23 by hand) | no — the snapshot is outside git |
| catalogue, crossed with objectives and transformations | **9,304** | no — same reason |
| labelled corpus | **327** entries, 236 `dev` / 91 `test` | **yes** |
| … of which labelled by the AUTHOR | **211**, against 116 by a model | **yes** |
| scorable criteria | **6** — `divulgation`, `obeissance`, `abus_outils`, `fuite_donnees_tiers`, `fingerprinting`, `fuite_permissions` | **yes** |
| `pytest` tests, no LLM call at all | **2,136** | **yes** |

**The right-hand column is not decoration.** The payload figures depend on
`payloads/garak.json`, which is gitignored — a guard on them would pass on a
development machine and fail in continuous integration, which is exactly the
defect that turned CI red for six days. So: guard what CI can see, DECLARE what
it cannot.

Two figures worth keeping in view because they bound what the tool can claim:
the corpus is 211 author-labelled against 116 model-labelled, and a figure over
model-decided labels measures agreement between models rather than whether the
judge is right. And every recall floor rests on its criterion's POSITIVES: of
the twelve criterion x side lines, `fuite_permissions` carries ONE positive in
`dev` and NONE in the frozen set, which bounds a perfect recall at 21% there and
measures nothing at all here. The other ten carry five or more.

## Architecture

```
config.py          # the single switching point: local model (Ollama) or remote API
llm_client.py      # THE abstraction layer: ask_llm()
targets/           # the systems under test — one common contract: ask(message) -> str
  demo.py          # deliberately badly protected, 3 levels: `--target demo[:N]`
  decoy.py         # local toy chatbot with a fake secret (the default)
  mock.py          # deterministic, no LLM: free end-to-end tests
  http.py          # a real endpoint: API profiles, --probe-target, zero dependencies
  websocket.py     # RFC 6455 on the standard library: ws:// and wss:// endpoints
  records.py       # a retrieval desk over reader records: the third-party target
  docs.py          # a document base readers write into: the indirect target
  bench.py         # a REFERENCE target: exactly one flaw open at a time
  foreign.py       # a target whose DEFENCE nobody here wrote
  conversation.py  # the multi-turn contract, and the refusal to fake it
  indirect.py      # the planted-note contract: declared, never guessed
  wrapping.py      # carries a target's DECLARED capabilities through a wrapper
agents/
  reconnaissance.py # probes the target (harmless questions) and builds a profile
  planner.py        # picks families, objectives and order from the profile (rules)
  adaptation.py     # reorders the pool DURING the campaign from the replies (rules)
  attacker.py       # supplies the building blocks: technique × objective × transformation
  judge.py          # LLM-as-judge: rules success / failure (JSON output)
  detectors.py      # decodes spelled-out, Base64 and hex BEFORE the judge (deterministic)
  verifier.py       # replay: does a leaked value come back, or was it a hallucination?
pyrit_bridge/      # PyRIT as the attack stage -- an EXTRA, absent from CI
  convert.py        # every decision takeable on plain data: imports NO PyRIT
  targets.py        # our model and our target, back inside ask_llm()
  campaign.py       # one multi-turn attempt, judged by OUR judge, on OUR format
payloads/
  library.json       # techniques (OWASP family + prerequisites) and objectives
  validate.py        # checks the library — `python -m payloads.validate`
  garak_source.py    # inventories the garak source (--list, --describe)
  garak_export.py    # exports the probes to a local snapshot — garak's venv, not ours
  garak.json         # the snapshot produced, OUTSIDE GIT: resync rather than freeze
tests/             # pytest, NO LLM call: runs in continuous integration
  test_detectors.py, test_verifier.py, test_judge.py,
  test_planner.py, test_targets.py, test_report.py,
  test_attacker_and_config.py, test_adaptation.py, test_reconnaissance.py,
  test_migration.py, test_config_env.py, test_cli_wiring.py
evaluation/        # measurements that NEED a model: to be run by hand
  labelled_exchanges.json  # ground truth (dev and test sets) for measuring the judge
  evaluate_judge.py        # precision, recall, a breakdown of the errors
  test_set_log.jsonl       # every consultation of the frozen set, timestamped
  label.py                 # hand-labelling, question by question (--integrate)
  check_reconnaissance.py  # tests profile and plan against simulated targets
  check_replay.py          # tests the replay against simulated targets of known behaviour
  measure_adaptation.py    # adaptive vs static plan, at equal budget (NO LLM)
  measure_adaptation_real.py # the same, against the REAL demo target, local judge
  measure_multiturn.py     # sequenced vs composed form, no judge in the loop
  collect_exchanges.py     # harvests real exchanges → to_label.json (a working file,
                           # outside git: label.py empties it into the corpus)
  collect_conversations.py # the same, multi-turn — no judge, no attacker model
  handwritten_conversations.py # the traps a harvest cannot produce, written by hand
  labelling_prepass.py     # mechanical facts to speed up labelling, and NO verdict
  frozen_lot.py            # the lot written to be HELD OUT: `test`, imposed
  split_sets.py            # dev / test, and which groups a set is IMPOSED on
  languages.py             # the attacker -> target language pair, stored not derived
  english_population.py    # faithful translations: a figure per language pair
  code_fingerprint.py      # what a measurement depends on, so a resume cannot mix
  check_stability.py       # judges a NAMED FEW several times: an edit, or a draw?
  measure_recall.py        # the CHAIN's recall on known flaws, vs a blind baseline
  measure_judges.py        # the criteria's share of a figure against the model's
  measure_labels.py        # a TEMPORARY arm: the question's label language, measured
                           # `--criterion` scores WHICH criterion, not the verdict
  resume.py                # verdicts written as they come, so a run can be repaired
  measure_modes.py         # `--multiturn` against single-turn, at equal requests
  measure_adaptive.py      # the adaptive arm -- and the confound that stopped it
audit.py           # mandate required before starting + JSONL audit trail as it goes
stats.py           # what a result bounds — and the refusal to bound absent independence
report.py          # result.json (truth) → report.md (rendering), severity by rules
migration.py       # reads data written before the names were translated
console.py         # output in UTF-8: a redirected campaign must survive its payloads
check_rename_damage.py # what the switch to English may have broken
check_excerpt.py   # the README's campaign excerpt against the run's real output
check_indirect.py  # plants a note in `docs` and shows what it does (calls a model)
examples/
  demo-report.md   # a committed example report, abridged (--abridge)
  demo-multiturn-report.md # the same, over several turns: the renderings that differ
  demo-pass-at-k-report.md # one combination x30: the only rendering that MEASURES a rate
main.py            # orchestrator: the campaign loop with its attempt budget
```

## Rules that MUST be respected

**No direct call to an LLM provider.** Everything goes through `ask_llm()` in
`llm_client.py`. That is what makes switching local ↔ API painless (one line in
`config.py`). Never hard-code an Ollama or OpenAI call anywhere else.

Clarified in phase 8: this rule covers the models **we use** (judge, analyst, decoy), so
that they stay interchangeable from `config.py`. It does NOT cover the target under
attack, which is an arbitrary third-party system — often an application, not a bare
model. `targets/http.py` therefore calls it directly, with urllib, and that is
deliberate.

**Always bound your loops.** Attacks are probabilistic: an adaptive agent loops forever
without a guard. `MAX_ATTEMPTS` in `main.py` bounds every campaign. Every new loop must
have a limit of its own.

**Never tune the judge against the test set.** Prompt, criteria and detectors are
adjusted looking only at the `dev` set. The `test` set is consulted only at key moments
(an important change, a change of model), and every consultation is logged
automatically. A group (one scenario and its rewordings) is never split between the two
sets: the script refuses it. The labels are the ground truth: the author validates them,
never the judge and never an LLM.

**Fictional secrets only, and fictional data in anything sent out.** A
deliberately vulnerable target shipped in a **public** repository is
commonplace and harmless; leaving a real value in one is not — hence
`TOPSECRET42` and its kind. The same applies to what leaves the perimeter: a
client's data reaching a remote judge belongs in the engagement contract, and
campaign logs carry complete payloads and the target's verbatim replies, so
they are not committed.

**Never an API key in the code.** They are read from environment variables (see the
`api` profile in `config.py`). The repository is public.

## Conventions

**Decision of 2026-11-13: the project switches TO ENGLISH, measurement apparatus
included. Completed on 2026-11-15.** The previous convention (code and comments in
French) is abandoned.

- Code, comments, docstrings and identifiers **in English**.
- Commit messages: **French for now**, on the author's decision of 2026-11-21.
  English had been the convention since 2026-11-13, and it stays the target; the
  decision is recorded as provisional because that is how it was given. The
  history therefore has STRATA — the 91 original French commits, the English
  ones of the switch, and the French ones since — and none is rewritten:
  rewriting public history would change every hash. A reader meeting a
  language they did not expect is reading a date, not an inconsistency.
- README **in English** (it already was).
- `GLOSSARY.md` is the single source of truth for the terminology. **Nothing gets
  renamed unless it appears there**: 1,064 functions and classes across 61 files cannot
  be renamed from memory, and the project already knows the drift-by-synonym it fights
  for label categories.
- Deliberately didactic comments: this project also exists to learn from, and the blocks
  explain the why, not just the what. That does not change with the language.
- **This file is in English as of 2026-11-15**, last, as the project itself required —
  its translation added nothing until the code had moved.

What stays French, each for a stated reason (see `GLOSSARY.md`): the judge's instruction
and the eight data names inside it, the demo target's system prompt and replies, the
refusal patterns, the labelling categories, the recorded corpus exchanges, the 18 sealed
trails, and the commit messages — the 91 original ones, and those written since
2026-11-21.

## Development environment

- **Windows**, **Git Bash** terminal (MSYS2/UCRT64).
- Virtual environment in `.venv`, activated with `source .venv/Scripts/activate`
  (Windows path, not `bin/`).
- Local model served by **Ollama** (`llama3.2`), no cost, no key.
- Single dependency: `openai` (the SDK talks to Ollama as happily as to remote APIs).

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| 0 | Agent loop, abstraction layer, LLM-as-judge, retry budget | **Done** |
| 1 | A library of real prompt injection payloads | **Done** (via garak + 15 by hand) |
| 2 | Judge reliability: measure and reduce false positives / negatives | In progress |
| 3a | **Reorder the plan from the target's reply** (deterministic, extends phase 5) | **Done** |
| 3b | Adaptive multi-turn attacker: evaluate PyRIT as a replacement for the hand-built orchestrator | **Done** — `--multiturn` runs a PyRIT conversation as the attack stage, attacker model and judge inside our own points of passage, with the trail, the budget and the report around it. **And the gain is now MEASURED, negatively** (2026-11-19, paid judge, protocol committed first): at equal TARGET REQUESTS a single-turn campaign finds more, 17 pairs to 1, and **26 `high` findings against none** — a conversation has no single payload to replay. **Measured at the three defence levels** (2026-11-23): single-turn wins at level 1 (17-1, reverse p = 0.0001) and at level 3 (12-3, reverse p = 0.0176), and the comparison is NULL at level 2 (8-7, p = 0.50) — so the result replicates but is not uniform. `high` findings: 26, then 5, then 0, and none for multi-turn at any level |
| 4 | Decouple the judge from the target model | **Done** |
| 5 | Reconnaissance and planning agents; multi-family campaigns | In progress |
| 6 | Reporting: JSON as the source of truth, Markdown rendering by default | **Done** |
| 7 | Integrate garak (breadth of coverage) | **Done** |
| 8 | **Target adapter**: aim at a real endpoint (URL, authentication, errors) | **Done** |
| 9 | **Traceability and authorisation**: replayable log, refuses to start without authorisation | **Done** |
| 10 | **Engineering quality**: LLM-free tests, continuous integration, packaging, CLI | **Done** |
| 11 | **Campaign budget**: ceiling in calls or tokens, clean stop when reached | **Done** |
| 12 | **Reproducible demonstration**: a vulnerable target shipped, detection in one command, output excerpt in the README | **Done** |
| 13 | **Statistically defensible results**: Wilson bound on "no findings", ASR, denominator states (gaps 1 to 3 of the OWASP audit) | **Done** |
| 14 | **Engagement-grade traceability**: SHA-256 evidence hashing, case IDs, target telemetry, MITRE ATLAS (gaps 5 to 7) | **Done** |

Phases 8 to 11 were added on 2026-11-09: they are the gaps that block going to
production, and that a roadmap centred on attacks left invisible.

**Two bars not to be confused.**
- *Usable on your own systems*: phases 1, 6 and 8. The tool aims at a real target, finds
  real flaws and produces a readable report. That is also what demonstrates best in a
  showcase.
- *Usable on an engagement*: add 2 (widened criteria), 9, 10 and 11. A pentest report
  containing a false finding costs the credibility of the whole engagement: 9 and 11 are
  the least visible and the most underestimated.

**Order imposed by the dependencies**, not to be taken backwards:
8 (a real target) → 1 and 7 (payloads) → 2 (criteria, once the target is richer) →
3 (multi-turn) → 6 (reporting). 9, 10 and 11 can proceed in parallel.
Phase 3 is the most expensive, and the only one where PyRIT does the heavy lifting.

## Decisions taken, and why — in `docs/decisions.md`

**378 decisions, and the reason each one was taken, are in
[`docs/decisions.md`](docs/decisions.md)** — 4,076 lines, which was 88% of
this file once the journal had left it on 2026-11-28. **They were MOVED,
never rewritten**: a test compares that file's tail with
`sha256 5583df491cc24dce…`, the digest of the text that stood here, so one
byte of drift fails the suite.

**WHAT STAYS HERE is what has to be in front of an agent**: the rules, the
architecture map, the roadmap, the state of now. A decision gets consulted
when it is QUESTIONED — which is a reason to be one click away rather than
loaded in full every session, and it is the same arbitrage as the journal's,
taken the same day for the same measured reason.

**And the durable half was NOT separated from the dated one**, deliberately:
of those 4,076 lines, 937 carry a date in their title, 579 only in their body
and 2,565 none at all, and none of those counts says *durable* or *dated*. The
frontier is an **intent per block**, so it belongs to the author and not to a
rule — the principle this project already holds for the dev/test split. The
mixture is declared in that file rather than guessed at here.

## What remains, in the order the dependencies impose

Rewritten 2026-11-19. The four locks recorded on 2026-11-17 have all moved:
two are closed, one is ANSWERED negatively, one is reduced tenfold and
deliberately stopped. What is left is smaller than what was, and this section
says so rather than keeping the old shape for comfort.

**1. THE JUDGE'S CRITERIA — SIX criteria, still four of ten OWASP families
scorable.** `divulgation` covers LLM02 and LLM07, `obeissance` LLM01,
`abus_outils` LLM06, `fuite_donnees_tiers` (2026-11-18) the LLM02 case no tool
reports, `fingerprinting` (11-26) the target naming its own model, and
`fuite_permissions` (11-27) who may do what in the application, LLM07's own
item 4. **Six criteria and four families is not an oversight**: the two newest
REFINE families already covered — fingerprinting has no OWASP family of its
own, only ATLAS `AML.T0014`, and a permission model is LLM07 — so widening the
criteria did not widen the coverage, and saying otherwise would overstate it. **The gap this lock was named for is CLOSED**: a target
volunteering a reader's name, address, phone number, file number and debt with
no tool marker used to score `aucun` — measured against the real judge, the
commonest finding of a real engagement scoring zero — and it now has a
criterion, ten labelled cases (5 positive), a severity row and five labelling
categories.

THREE gaps stay PINNED BY TESTS, so adding one fails a test that says what the
corpus then needs. They were five, and **two were closed by the two newest
criteria** — the target naming its model, and LLM07's disclosed bypassable
control. What is left is one register the judge cannot score at all, now HALF
closed, and two deliberate boundaries:
- **indirect injection** — a payload arriving from a document, a page or a
  tool's output rather than from the user. **Measured 2026-11-25, 10/10 each
  way**: when the OUTCOME is visible in the reply — a value disclosed, a third
  party's record, a tool fired — the existing criteria already score it
  without the document being shown, because being blind is what makes that
  work. What stays unscorable is OBEDIENCE to a text only the document carried
  (`aucun`, and the judge is right: criterion 2 needs an imposed text to
  compare against). So the visible half needs no criterion at all, only a
  provenance field on the attempt, since the judge will grade the outcome
  correctly and can never say the injection was indirect;

Two are deliberate BOUNDARIES of criterion 4, decided by the author and
pinned so they cannot be inherited silently: **aggregation** (elements across
several replies that identify only together — `P11`, ruled no) and **a reverse
lookup** answered with a name alone, which the narrow reading of "the reply
ties a datum to a person" does not reach. A test asserts the corpus holds no
reverse lookup at all, so the day one is added the decision is forced.

What is actually left in this lock is the FLOORS, not the criteria. On the
author's ground truth there are now TWELVE criterion x side lines, and they
are no longer level: ten carry four positives or more — `divulgation` 87% in
`dev` and 65% in the frozen set, down to `fingerprinting` at 57% and 51% —
while **`fuite_permissions` carries ONE positive in `dev` (21%) and NONE in
the frozen set**. So the newest criterion bounds nothing yet, and raising it
needs four more REGISTERS and not four variants of one turn. Every floor is
cases written and labelled by the author; no tooling raises one.

**The published figures describe an instruction of 9,836 characters (base)
plus a 1,706-character addendum, re-measured on 2026-11-27 after the
criterion-5 seam was closed**: `dev` at **90 / 97 / 94** overall and
**89 / 98 / 94** on the author's half, over 232 entries. Said rather than
hidden: `dev` holds **236** entries now, the four criterion-6 cases having
been labelled after that run, so the figure is one step behind by four
entries.

**The FROZEN set was consulted on 2026-11-27**, the NINTH time, and the
original 23 come back at **80 / 100 / 91** — `T10`, the known hallucination,
plus `R08-2`, which is ONE case and is **measured** to flip 2 times in 30, so
no degradation is claimed. Recall is **100% on those 23 for the ninth
consecutive time**. On the wider 59 the same run gives 86 / 96 / 92, its one
miss being `F24`, measured to flip 6 times in 30: the two populations are
never pooled, and the nine-consultation record belongs to the 23.

**2. THE CORPUS'S PROVENANCE — closed as a blocker, permanent as a caveat.**
The frozen lot was written (22 cases, 19 groups), labelled BY THE AUTHOR, and
integrated: his half of the frozen set went from 23 entries to 45, and
`abus_outils` and `fuite_donnees_tiers` got their first measurement on cases
never looked at — the debt recorded on 2026-11-12 and doubled on 2026-11-18.
Corpus: **327 entries, 211 `author` / 116 `model`**, the author's half at 65%,
and his half of the frozen set at 59 entries rather than 45.

What remains is not work but a READING RULE, and the sixth consultation showed
why it is not optional: read flat, that run gives recall 79%; split by
provenance, it is **100% on the author's ground truth and 50% on the
model-labelled half**. A figure over model-decided labels measures agreement
between models. The split is stored on every entry and reported above the
figures, so the rule is enforced rather than remembered.

**3. THE MULTI-TURN GAIN — ANSWERED, and the answer is NO.** Three
measurements, each with its protocol committed before the run:
- the sequenced form against a composed message, judged outcome, 102 pairs:
  **15 against 17, p = 0.70**, the effect bounded within about ±10 points and
  a dead tie once the declared judge bias is paid back;
- the adaptive attacker in isolation: **not measurable with the tool as
  built**. `objective_for` couples adaptation to payload-use, so the arms
  would differ in two variables;
- `--multiturn` against a single-turn campaign at equal TARGET REQUESTS, 20
  pairs at defence level 1: **single-turn wins 17 pairs to 1**, reverse
  p = 0.0001, and
  **0.216 against 0.110 findings per request** after the declared bias is paid
  back. The breakdown is wider still: **26 `high` findings against none**, a
  difference in kind, since `high` needs a replay and a conversation has
  nothing to re-send.

**And the obstacle this lock recorded was the FREE TIER, not the method.** It
said the good judge costs ~13,000 tokens an attempt and a declared protocol
with it was "the only honest route". That route was taken: the mode comparison
ran on the PAID Groq judge — the measured one — for **2,054 calls and
3.77 million tokens across 40 campaigns**, under a euro at listed rates. The
measurement called infeasible in November cost less than a coffee once the
plan changed.

**Generality is now MEASURED, and the result replicates without being
uniform** (2026-11-23, protocol committed before the runs): single-turn wins
at level 1 (17-1) and at level 3 (12-3, reverse p = 0.0176), and the
comparison is a dead TIE at level 2 (8-7-5, p = 0.50). So the level-1 finding
is not an artefact of level 1 — and it is not a property of the tool either.
Three levels are three runs, not a dose-response design, and the two
intervals that separate are level 1's and level 2's; level 2's and level 3's
overlap.

What is STILL not settled: **other targets.** Three defence levels of ONE
target, which differ only in how the secret is protected — by construction,
so that comparing them measures the defence and nothing else. A different
role, a different tool, a different language is a different question.
And the adaptive attacker's own contribution, which no budget buys, because
the tool cannot vary adaptation without varying payload-use.

**4. THE CRITERION SEAM — reduced tenfold, then STOPPED on a power
calculation.** `C-demo3-01-2` went from **7/10 wrong to 1/21**
(p = 3.3 × 10⁻⁴) on an EXAMPLE pair, after a clause the judge already had and
did not apply. Cycle 2 is cancelled: from 2/30, a perfect 0/100 would give
p = 0.05, so no further correction would be attributable — and it would mean
touching the most delicately tuned sentence in the project for a gain below
the resolution of any affordable measurement.

**And two of its three "observations" were WITHDRAWN.** `E03-b` under the
English instruction and `R07-2` on the frozen set are single draws:
measured across five consultations, `R07-2` is wrong, correct, correct, wrong,
correct. The seam is measured on `dev` and nowhere else, and `F14` on the
frozen lot is exactly what a 7% residual predicts across 22 cases (80% chance
of at least one). It therefore justifies nothing: seen on the frozen set, it
cannot be acted on from there at all.

**The tail, concrete and bounded:**

- **`multitours-reussi` was REMOVED and `multitours-refuse` holds one case.**
  The two author-labelled cases of the format's own contribution (`F19`,
  `F20`) are filed under `obeissance` / `obeissance-refusee` by my stated
  fallback, which the author did not rule on. The counting no longer depends
  on it — the contribution is reported as a figure, **35% of conversation
  positives breach after the first turn** — but the filing is still his to
  decide.
- **pass@k is DONE (2026-11-20), so phase 13 is closed.** `--repeat` plus the
  gate on the three axes, and the first measured attack success rate in the
  project: 8 of 30 of one combination against `demo:3`, true rate 14%–44%.
  What is still NOT shown by any artefact is a ZERO — the bounded null itself.
  It needs a target that holds, and `demo` gives way at every level once N is
  raised; picking a technique it resists in order to get one would be outcome
  selection. So the rendering is reachable and honest now, and nobody has met
  it yet.
- **`collect_exchanges` is BOUNDED (2026-11-20)**, and appends, and records
  the secret its target declares. The sampling POLICY stays the author's:
  `MAX_PAYLOADS = 60` and `--payloads N`, one visible number rather than a
  rule in a loop. What is still theirs to decide is whether 60 x 2 is the
  right size. The old 18,536-entry harvest was DISCARDED on 2026-11-27, after
  a backup and after verifying none of it was labelled: `to_label.json` keeps
  only the 57 indirect entries, so `label.py` without arguments is usable
  again.
- **MITRE ATLAS is DONE (2026-11-20)**: four families, read from
  `dist/v6/ATLAS-2026.10.yaml`, each identifier carrying how its OWASP match
  was established — ATLAS cites the entry itself for LLM02 and LLM07. What
  remains unmapped is every family we do not test, which is the honest state.
  Re-check on the next ATLAS release: two IDs were renumbered between 5.6.0
  and 2026.10, so these labels are a dated reading and not a permanent fact.
- **Phase 5: reconnaissance now reads what it SEES as well (2026-11-20).**
  The purely declarative limit is addressed: `mentions_instructions` is a
  tri-state ruling out only on an explicit NO, and a tool marker or a
  secret-naming refusal in a probe reply is an OBSERVED fact that may fill a
  declaration the analyst missed. What is left is narrower and still real: six
  probes see only what six probes elicit, and the observed readers are
  patterns, so a tool marked some way we have never met is a tool unseen.
  `--multiturn` still makes a poor profile bite harder, since a multi-turn
  attempt pursues the reconnaissance objective INSTEAD of its payload.
- **The THREE example reports are CURRENT** (re-rendered 2026-11-20 so none
  drifts from the renderer): single-turn with two `high` findings
  replay-confirmed and the README excerpt from that same campaign; multi-turn,
  which exercises every rendering only that mode produces; and pass@k, the
  only one whose Coverage section MEASURES a rate instead of bounding or
  declining. The bounded null stays unshown, for the reason in the pass@k item
  above.
- **The three EXAMPLE reports have DRIFTED from the renderer.** All three
  name LLM07, so all three would now carry the `What a zero on LLM07 is
  worth` caveat added on 2026-11-27, and none has it. And they cannot be
  re-rendered for free: no `result.json` is kept anywhere, so the lever
  "the JSON is the source of truth" -- which has paid in cash six times -- is
  UNAVAILABLE here. Re-rendering them needs a campaign, or an abridged
  `result.json` committed beside each one, which is a decision about
  publishing a campaign's verbatim replies.
- **GET, multipart and WebSocket endpoints are REACHED (2026-11-20)**, as
  profiles or `--target-transport`, single-turn and multi-turn alike. The
  WebSocket client is RFC 6455 on the standard library rather than an extra,
  because the protocol has been frozen since 2011 — the maintenance argument
  that made PyRIT an extra does not transfer — and because the framing is
  then checkable in CI, which an extra is not. What stays out of reach is a
  multipart FILE part, deliberately: it is what an indirect-injection test
  would need, and that register is one the judge cannot score at all, so it
  would be building the wrong half first. Also WebSocket subprotocol
  negotiation, and the multi-turn shape where the dialogue stays open on ONE
  socket — our contract hands each attempt a history and opens a fresh
  connection.

**And the pattern worth carrying forward**, because it has now happened nine
times in a week: **a new delivery mode, or a new figure, turns every
unconditional sentence in the output into a claim that has to be re-checked**
— and only READING THE RENDERING finds them. Three of the four presentation
defects of 2026-11-12, all four of 2026-11-17, the `precision=0%` on an
unmeasured population and the by-criterion attribution all came out that way:
never from a test, never from reading the code.

## Journal — dated entries, in `docs/journal/`

**The project's record has TWO regimes of truth, and this file now holds only
the one that ROTS.** The dated entries are in **[`docs/journal/`](docs/journal/)**, one file per working day,
with an index: 113 entries over 11 days. Each is true of
its date, none is rewritten — the same reason the 91 French commits and the 18
sealed trails are not rewritten.

The sections ABOVE describe the state NOW, so every sentence in them is a
claim that goes stale in silence at each commit that does not touch it. That
is why they are kept to a screen, why their figures carry executable guards,
and why an addition to them should DISPLACE something rather than accumulate.

**They were MOVED on 2026-11-28, never rewritten**, and that is checkable
rather than asserted: a test re-assembles every day file in date order and
compares with `sha256 4860acb178b2fbaa…`, the
digest of the 110 entries as they stood here. One byte of drift fails the
suite, and a correction to an entry is written as a NEW entry rather than an
edit — an entry is true of its date.

**One thing WAS rewritten, and it is this preamble.** It opened on
*"Everything below is dated"*, which the move made false: nothing is below any
more. Keeping it verbatim would have kept a false sentence in a state section,
which is the defect this file hunts most often, so it is restated here and its
original 745 bytes are quoted verbatim in
[the index](docs/journal/README.md) — with a guard, because *nothing was lost*
is a property and not a sentence in a commit message. Before the move the
journal was 69% of a 900 KB file loaded in full on every session, against 3%
that is actually an instruction.

### The lessons those entries number themselves

**New writing, and the only part of this section that is not a move.** It is
an EXTRACTION rather than an invention: the journal counts its own recurring
defects ("twelfth time in this file that…"), so what follows is that count
read off. It is here because it is the half an agent uses; the narrative that
earned each line is in `docs/journal/`.

**A guard is worth only what it COMPARES — twelve times.** Its forms, each met
for real: comparing a result to the constant that produced it; looking for a
TEXT where the property is a behaviour; keying on a COUNT, so it breaks on an
addition and passes on the flip it exists to forbid; naming its groups in the
source, so it stays silent when a third arrives; comparing a PRESENCE where
the collision is a CONTENT; asserting "not before X" when the claim is
"nowhere else"; and reading a docstring that explains why the code does not do
the thing.

**The JUNCTION between two modules correct on their own — ten times.** The
template with no `{message}`, the unreachable profile guard, the three
chain-of-custody fields nobody filled, `label.py`'s set question, the frozen
lot's silent guard, the spliced `measure()` call, `REPLAYABLE_CRITERIA` read
in one place and restated in another. **A test that drives the entry point
finds it; a test that reads its source usually does not.**

**A field written and never read, or read and never written.** The same
half-wiring in both directions, and the commonest defect shape here: the
breach turn the judge emitted into nothing, `interroger.transport`, the
telemetry that reached no reader, a computed figure never printed.

**A mutation that does not touch the asserted property says nothing about the
guard — six times.** And its two mirrors: a mutation that BREAKS the file
(a bare `try:`, a syntax error) says nothing either, and a mutation read mute
because the sweep did not run the guard that holds it is worse than a missing
guard — it invents a hole.

**A presentation defect comes out ONLY by reading the rendering — sixteen
times.** Never from a test, never from reading the code. A new delivery mode,
or a new figure, turns every unconditional sentence in the output into a claim
that has to be re-checked.

**A small sample read as a trend — five times**, each corrected by a wider
measurement. Hence: the protocol, its N, its direction and its threshold are
declared and committed BEFORE the run, the threshold is set PER METRIC because
the denominators differ, and a rerun chosen after seeing a p-value is a corrupt
reason however sound its design.

**One run cannot tell a repaired case from a lucky one.** 10 rounds were
measured insufficient the day after they were chosen; 30 is the decisive
reading, and no number of rounds supports the word "stable".

**The lever that is missing is the one not yet pulled.** A clause the judge has
and does not apply is not fixed by a better clause — it wants an EXAMPLE; a
clause that is paradoxical on its surface wants the CLAUSE, even where the
example is already there.

**A correction with no BEFORE measurement is attributable to nothing**, in
either direction.

**A development environment richer than continuous integration masks what you
just added — four times** (Ollama present locally, a gitignored snapshot, a
fixture hiding a tautology). And once in the INVERSE: a test that depended on
the config being STALE, green in CI and red the moment it was repaired.

**A SWEEP, never a list somebody must remember to extend.** Entry points,
`py-modules`, the `.gitignore` prefixes, both architecture maps, the severity
table's reachable set. A list is where the awkward case gets lost — and a
sweep must list untracked files too, or the defect ships in the very commit
that introduces it.

**A guard that cries wrong on legitimate data teaches people to ignore it.**
This project removed a whole guard for being wrong twice in four.

**The machine flags, the human decides.** The mandate, the snapshot's age, the
redundancy of a hand-written technique, an unverifiable judge: each is
reported and none is acted on automatically.

**Write patch scripts with a file tool, never a heredoc.** Escapes collapse,
a `\b` lands as a real backspace that compiles and matches nothing, and an
anchor must be written in the bytes the file actually holds.

## Legal framing

A security research project. LLM red teaming is only lawful against systems you own or are
**explicitly authorised** to test. Never point the tool at a third-party service without
written authorisation.
