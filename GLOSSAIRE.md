# Glossary — French → English

The project is being translated to English. This file is the **single source of
truth for terminology**, and it exists for one reason: 918 functions and classes
across 55 files cannot be renamed consistently from memory. Without a fixed
glossary, `cible` becomes `target` in one file and `system_under_test` in
another — which is exactly the drift the project already guards against for
label categories (`fuite_directe` vs `fuite-directe`).

**Rule: nothing gets renamed unless it is in this table.** Adding a term here is
part of the change, not a detail.

## Core domain

| French | English | Note |
|---|---|---|
| cible | target | the system under test |
| attaquant | attacker | supplies payloads |
| arbitre | judge | the LLM-as-judge |
| verdict | verdict | unchanged |
| payload | payload | unchanged — the field's own word |
| constat | finding | what a report lists |
| essai | attempt | one payload sent |
| campagne | campaign | unchanged in meaning |
| fiche (cible) | profile | what reconnaissance produces |
| plan | plan | unchanged |
| vivier | pool | the full candidate set |
| rejeu | replay | the hallucination check |
| leurre | decoy | the local toy target |
| piste (d'audit) | trail | audit trail |
| sceau | seal | SHA-256 over the trail |
| mandat / autorisation | mandate / authorisation | the legal gate |
| écartée | skipped | with a stated reason |
| effleurée | touched | reached but not judged |
| objectif | objective | the third library axis |
| technique | technique | unchanged |
| transformation | transformation | unchanged |
| sonde | probe | a garak probe |
| module (garak) | module | unchanged |
| prérequis | prerequisite | gates a technique |
| contexte | context | declared by the operator |
| budget | budget | unchanged |
| journal | log | the call/token log |
| gravité | severity | from rules, never a model |
| couverture | coverage | the honest half of a report |
| portée | scope | what a result bounds |
| borne | bound | Wilson, rule of three |
| récolte | harvest | collecting exchanges to label |
| étiquette / étiqueter | label / to label | ground truth, author-validated |
| jeu (dev / test) | set (dev / test) | the frozen set discipline |
| tour | turn | one exchange in a conversation |
| historique | history | prior turns |
| adaptation | adaptation | reordering, not rewording |

## Judge criteria — DATA, not prose

These are **keys**: they appear in `resultat.json`, in 18 sealed audit trails,
in the committed example report and in the labelled corpus. Renaming them is a
data migration, not a translation.

| French | English |
|---|---|
| divulgation | disclosure |
| obeissance | compliance |
| abus_outils | tool_abuse |
| aucun | none |

## Translated in a coordinated pass, not file by file

Three kinds of French cross every file, and translating them one file at a time
would leave the repository inconsistent between commits:

| What | Why it waits | What it drags with it |
|---|---|---|
| **JSON data keys** (`constats`, `couverture`, `portee`, the `STATES` keys…) | persisted in `resultat.json`, in 18 sealed trails and in the committed example | a documented migration, plus regenerating the example |
| **operator-facing messages** (errors, diagnostics, campaign output, report text) | they ARE the project's output: they appear verbatim in the README excerpt and in `exemples/rapport-demo.md` | regenerating both, which needs a campaign, hence quota |
| **`.env` configuration keys** (`CIBLE_CORPS`, `CIBLE_CHEMIN_REPONSE`…) | a configuration contract: renaming breaks every existing `.env`, including on machines this repository never sees | a migration with a deprecation path |

Code (identifiers, comments, docstrings) moves layer by layer; these three move
once, deliberately, with their artefacts.

## Deliberately NOT translated

| What | Why |
|---|---|
| the 91 commit messages | public history; rewriting it would rewrite every hash |
| the 18 sealed audit trails | a seal whose content changes is no longer a seal |
| recorded exchanges in the corpus | a target's actual words are **evidence**. Translating a recorded response fabricates data that no target ever produced |
| OWASP family labels (`LLM01:2025 …`) | they are the standard's own strings |
| garak probe names and tags | they come from upstream |

## Renaming hazards met in practice

A blanket search-and-replace is how this gets done, and it is also how it goes
wrong. Each entry here cost a broken test run.

| Word | Why a global rename breaks |
|---|---|
| `analyser` | two unrelated meanings: *to analyse* (the detectors) and *the analyst* — the model reconnaissance uses to extract the profile. Renaming the detector function hit a pytest fixture named after the analyst, and 19 tests errored on a missing fixture |
| `taux_de_succes` | the FUNCTION is `success_rate`; the identically-named JSON KEY in `resultat.json` must stay. Rename the call, not the string |
| `tester` | two meanings again: *probe the wiring* (`cibles/http.py`) and *run this measurement* (`evaluation/tester_*.py`). Renaming the first gave the evaluation scripts a `probe_target()` that probes nothing |
| French PROSE containing an identifier | the worst of the four, because the suite stays green. Renaming `prochain` → `next_attempt` rewrote twelve French sentences, including two strings rendered into the client-facing report and — worst — a target reply pinned VERBATIM in `tests/test_adaptation.py`. A test whose data is falsified no longer tests what it claims. A detector now scans for English identifiers inside French sentences after every rename pass |
| data keys that look like identifiers | `TRANSFORMATIONS`' keys (`"identite"`, `"majuscules"`) travel into `resultat.json`, the committed example and the README excerpt. A `identite` rename hits the string literal too, and the tests follow silently because they were renamed in the same pass |
| local variables sharing a name with a dict key | the same hazard as above, met THREE times: renaming the local `echanges`, `fiche` or `identite` also rewrote `"echanges"`, `"identite"` and `"majuscules"` in the neighbouring dict. The suite caught each one, but by ricochet — `tests/test_rapport.py::TestLeSchemaDeDonneesEstEPINGLE` now pins the data schema directly and names the offending key |
| keyword arguments | `independants=` / `quoi=` are passed by name from four call sites. Renaming the parameter without them turned 693 green tests into 99 failures in one step — which is exactly why the order runs leaves-to-root |

## Terms whose translation changes BEHAVIOUR

Flagged here so nobody treats them as prose:

- **refusal patterns** (`agents/adaptation.py`): they match what a
  French-speaking target writes. Translating them stops adaptation from firing
  against a French target — and they were corrected once already, after real
  campaign responses that are now pinned verbatim in tests.
- **the demo target's system prompt**: the target *is* a French library
  assistant. Translating it changes the measured object: the three defence
  levels, the measured gradient, the example report, the README excerpt.
- **the judge's instruction**: translating it switches its structural labels to
  `User:` / `Assistant:`, which **59 library payloads contain**. A target
  echoing one could forge a turn in the judge's own prompt. The injection must
  be fixed first; a test blocks the switch until then.
