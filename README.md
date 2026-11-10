# LLM Red Team Agents

[![tests](https://github.com/mchx-cs/agentic-llm-redteam/actions/workflows/tests.yml/badge.svg)](https://github.com/mchx-cs/agentic-llm-redteam/actions/workflows/tests.yml)

A multi-agent system that automates adversarial security testing of LLM applications — give it an endpoint, get back a list of validated vulnerabilities.

> **Status: the campaign pipeline is complete; the attack library is not.**
> Reconnaissance → planning → attack → judgement → replay verification runs end to end,
> against the bundled decoy or any HTTP endpoint. The judge is measured on 80
> hand-labelled exchanges, reaching 96% accuracy on the frozen test set; it classifies
> translated cases in English as accurately as their French originals.
> What is still missing is the attack content itself: the payload families are declared
> but empty, so a campaign today only sends harmless control prompts.
> See the [roadmap](#roadmap) for what is and isn't implemented.

---

## Why this project

Classic web penetration testing looks for flaws in *code*: an SQL injection either
works or it doesn't. Testing an LLM application is a different problem — the system
is **probabilistic**. The same prompt injection may succeed one time in three, and
there is no clean proof of exploitation: the output is free-form text.

That raises the question this project is built around:

**How do you decide, automatically, that an attack succeeded?**

The answer used across the field is an *LLM-as-judge* — a second model that reads the
exchange and rules on it. Making that judge reliable is the core technical challenge,
and the reason this repository exists.

## Architecture

A set of specialised agents, each owning one phase. The planner selects and orders the
attempts; a fixed budget bounds every campaign. (Reformulating a failed attempt from the
target's reply is phase 3 — the arrow below is the intended design, not today's code.)

```mermaid
flowchart TD
    A([Target LLM endpoint]) --> B[Reconnaissance<br/><i>probe behaviour, fingerprint guardrails</i>]
    B --> C[Planning<br/><i>select attack families to run</i>]
    C --> D[Attack<br/><i>generate and send payloads</i>]
    D --> E[Target responds]
    E --> F{Judge<br/><i>LLM-as-judge: did it break?</i>}
    F -->|vulnerability confirmed| G[Report<br/><i>findings with evidence</i>]
    F -->|no breach, retry budget left| D
    F -->|budget exhausted| G
```

Two design decisions worth calling out:

**A single abstraction layer for every model call.** Every call to a model *we* run —
judge, reconnaissance analyst, decoy — goes through `demander_au_llm()` in
`llm_client.py`, so switching provider is a `.env` change and nothing else in the
codebase moves. The system *under test* is deliberately outside that rule: it is a
third-party application, reached through its own adapter in `cibles/`.

**An explicit retry budget.** Because attacks are probabilistic, an adaptive agent will
happily loop forever. `MAX_ESSAIS` bounds every campaign — a correctness concern as much
as a cost one.

## Attack surface targeted

Testing follows the [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/):

- Prompt injection — overriding the application's instructions
- Jailbreaks — bypassing safety guardrails
- System prompt leakage — extracting hidden instructions
- Sensitive information disclosure
- Insecure output handling *(planned)*

## Project structure

```
.
├── config.py          # provider profiles and target selection, all driven by .env
├── llm_client.py      # the abstraction layer — every model call goes through here
├── cibles/            # systems under test — one contract: interroger(message) -> str
│   ├── leurre.py      # local decoy chatbot holding a fake secret (default)
│   ├── mock.py        # deterministic, no LLM: free end-to-end tests
│   └── http.py        # a real endpoint, described in .env (urllib, no new dependency)
├── agents/
│   ├── reconnaissance.py # probes the target with harmless questions, builds a profile
│   ├── planificateur.py  # picks families, objectives and order from that profile (rules)
│   ├── attaquant.py   # supplies the building blocks: technique × objective × transformation
│   ├── arbitre.py     # LLM-as-judge: rules on success or failure (JSON verdict)
│   ├── detecteurs.py  # deterministic decoding (spelled-out, Base64, hex) before the judge
│   └── verificateur.py  # replay check: real leak or target hallucination?
├── payloads/
│   └── bibliotheque.json      # attack techniques (by OWASP family) and objectives
├── tests/             # pytest, no LLM calls — runs in CI on every push
├── evaluation/        # measurements that DO need a model — run by hand
│   ├── echanges_etiquetes.json  # hand-labelled exchanges (dev and frozen test sets)
│   ├── evaluer_arbitre.py       # measures judge precision and recall
│   ├── journal_test.jsonl       # timestamped log of every test-set run
│   ├── tester_rejeu.py          # tests the replay check against simulated targets
│   ├── tester_reconnaissance.py # tests profiling and planning against simulated targets
│   ├── collecter_echanges.py    # records real target exchanges for blind hand-labelling
│   └── etiqueter.py             # command-line hand-labelling, one question at a time
├── rapport.py         # resultat.json (source of truth) → rapport.md; rule-based severity
└── main.py            # orchestrator: runs the campaign loop
```

## Getting started

Runs fully locally, no API key and no cost, against a model served by [Ollama](https://ollama.com).

```bash
git clone https://github.com/mchx-cs/agentic-llm-redteam.git
cd agentic-llm-redteam

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

ollama pull llama3.2
python main.py
```

Expected output is the profile the reconnaissance agent built of the target, the plan
derived from it — including which attack families were ruled out and why — then each
attempt with the payload sent, the target's reply, and the judge's reasoned verdict.

To measure the judge against hand-labelled exchanges (precision, recall, and every
misclassification explained):

```bash
python -m evaluation.evaluer_arbitre          # development set: used to tune the judge
python -m evaluation.evaluer_arbitre --test   # frozen test set: never used for tuning
```

Verification is split in two, and the split matters.

**`tests/` never calls a model.** 124 pytest tests covering the detectors, the replay
logic, verdict parsing and vote arithmetic, the planner's rules, the target adapters and
the report's severity rules. They run in four seconds, cost nothing, and GitHub Actions
runs them on every push across Ubuntu and Windows, Python 3.10 and 3.13:

```bash
pip install -r requirements-dev.txt
pytest
```

They earned their keep immediately: the first run found that a whitespace-only value
passed as a verifiable secret, which would have let the replay check "confirm" a leak
against an empty string.

**`evaluation/` holds what genuinely needs a model** — judge accuracy, replay behaviour,
profiling — so it costs quota and cannot run in CI. These are run by hand:

```bash
python -m evaluation.tester_rejeu            # replay check
python -m evaluation.tester_reconnaissance   # profiling and planning
```

Those two use targets whose behaviour is known in advance: one that always leaks, one
that hallucinates a new password every time, one that declares tools, one that reveals
nothing.

Exchanges are grouped by scenario, and a scenario never spans both sets, so the test
set cannot contain a mere rewording of a case the judge was tuned on. Every test-set
run is logged with a timestamp in `evaluation/journal_test.jsonl`.

### Pointing at a real target

The target is an adapter, selected per run — nothing is hardcoded:

```bash
python main.py                          # the decoy, no setup required
python main.py --cible mock             # deterministic, no LLM, no quota
python main.py --cible https://host/chat  # a real endpoint
```

Applications all shape their JSON differently, so rather than guess, the shape is
described in `.env`:

```bash
CIBLE_ENTETES={"Authorization": "Bearer xxx"}
CIBLE_CORPS={"messages":[{"role":"user","content":"{message}"}]}
CIBLE_CHEMIN_REPONSE=choices.0.message.content
```

`{message}` is substituted into the parsed structure, not into raw text, so a payload
full of quotes and newlines travels intact and cannot inject JSON. Every failure —
HTTP error, unreachable host, non-JSON reply, wrong response path — is reported as an
instruction rather than a stack trace.

Only ever point this at a system you own or have **written authorisation** to test.

### Producing a report

```bash
python main.py --cible mock --rapport
```

The campaign runs its whole plan and collects every finding, then writes two files:
`resultat.json` is the source of truth, `rapport.md` is one rendering of it. Adding a
format later (HTML, or PDF through pandoc) is one more function, never a rewrite.

Severity comes from rules, not from a model: a leak whose value comes back on replay is
*high*; one the replay could not reproduce is *to verify*; obedience to an injected
instruction is *medium*. A penetration test whose severities change between runs is
indefensible, and the judge is already non-deterministic — stacking a second source of
variance on top of it would be worse.

Every report ends with what was **not** tested and why — a tool that hides its coverage
gives a false sense of security, which is worse than no report at all. With the payload
library still empty, that section is currently the longest part of the document.

### Switching to a hosted API

Every provider setting lives in `.env` (git-ignored), so switching never means editing
a tracked file. Copy `.env.example` to `.env` and fill in:

```bash
OPENAI_API_KEY=sk-...
OPENAI_MODEL=<model-name>
PROFIL_ACTIF=api
```

Two independent switches: `PROFIL_ACTIF` drives the decoy and any call that does not
name a profile, `PROFIL_ARBITRE` drives the judge. An unknown profile name fails at
import with the list of valid ones, rather than hours later on the first model call.

One distinction worth stating: a hosted profile is for the models *we* run. Trying to
make a provider's own model misbehave would breach their terms of service. Testing a
client application that happens to be built on such a provider is a different matter —
that is what the HTTP adapter above is for, and it needs the client's written
authorisation.

### Running the judge on a different model

A judge that shares its target's model shares its blind spots, so the judge has its own
profile. Copy `.env.example` to `.env` (git-ignored), add a free [Groq](https://console.groq.com)
API key, and set:

```bash
PROFIL_ARBITRE=groq
```

On the same prompt, moving the judge from local `llama3.2` (3B) to `gpt-oss-120b` raised
recall on the frozen test set from 50% to 100% (accuracy 73% → 93%). The remaining errors
are target hallucinations (a made-up password looks like a leak to a blind judge), which
call for verification by replay rather than a better prompt.

That replay check is in place: when the judge sees a leaked value, the same payload is
replayed a bounded number of times. A real secret comes back unchanged; a hallucinated
one changes every time. The leak is then reported as *confirmed*, *probable
hallucination* (the campaign moves on), *contradictory* or *inconclusive*.

The hosted judge only ever sees fictitious exchanges; the target under attack stays local.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **0** | Agent loop, abstraction layer, LLM-as-judge, retry budget | **Done** |
| **1** | Real prompt injection payload library | In progress |
| **2** | Judge reliability — measuring and reducing false positives/negatives | In progress |
| **3a** | Reorder the plan from the target's reply (deterministic; extends phase 5) | Planned |
| **3b** | Adaptive multi-turn attacker — evaluate [PyRIT](https://github.com/Azure/PyRIT) as a replacement for the hand-built orchestrator | Planned |
| **4** | Decouple judge from target model (a judge sharing its target's blind spots is a known bias) | In progress |
| **5** | Reconnaissance and planning agents; multi-family campaigns | In progress |
| **6** | Reporting — structured JSON as the source of truth, Markdown as the default rendering | **Done** |
| **7** | Integrate [garak](https://github.com/NVIDIA/garak) for vulnerability scanning breadth | Planned |
| **8** | Target adapter — point the tool at a real endpoint (URL, auth, error handling) | **Done** |
| **9** | Audit trail and authorisation — replayable campaign log, refuses to start unrecorded | Planned |
| **10** | Engineering baseline — LLM-free unit tests, CI, packaging, CLI entry point | **Done** |
| **11** | Campaign budget — hard ceiling in calls or tokens, clean stop when reached | Planned |
| **12** | Reproducible demo — a deliberately vulnerable target shipped with the project, one command to reproduce a detection, asciinema recording in this README | Planned |

Phases 1, 6 and 8 are what it takes to run the tool against systems you own. Phases 2,
9, 10 and 11 are what separates that from a tool fit for a client engagement: a
penetration test report containing one fabricated finding costs the credibility of the
whole engagement.

Dependencies run in one direction: 8 (real target) → 1 and 7 (payloads) → 2 (broader
judge criteria, once the target has tools and retrieval) → 3 (adaptation) → 6 (report).
Phases 9, 10 and 11 can proceed in parallel.

Phase 3 is split because "adaptive attacker" hides two very different price tags. 3a
reorders an existing plan from what the target just said — deterministic, cheap, and
something PyRIT does not do for you. 3b is genuine multi-turn conversation, and its real
cost is not the orchestrator but the judge: its prompt takes exactly one exchange today,
and all 80 labelled exchanges are single-turn, so the corpus has to be rebuilt and
relabelled by hand before any figure means anything again.

## Stack

Python · Ollama (local inference) · OpenAI-compatible API clients

Reference frameworks studied for this project: [garak](https://github.com/NVIDIA/garak)
(NVIDIA) for vulnerability scanning breadth, and [PyRIT](https://github.com/Azure/PyRIT)
(Microsoft) for multi-turn adversarial orchestration.

## Responsible use

This is a security research and learning project. LLM red teaming is lawful only
against systems you own or have **explicit written authorisation** to test — the same
framework that governs any penetration testing engagement. Use it on your own
deployments and purpose-built targets, never against a third-party service without
permission.

## License

Released under the [MIT License](LICENSE).

## Author

**Clément Monchaux** — cybersecurity student, focused on offensive security and AI security.
[LinkedIn](https://www.linkedin.com/in/cl%C3%A9ment-monchaux-64695119a)
