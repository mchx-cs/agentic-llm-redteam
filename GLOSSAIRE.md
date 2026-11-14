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
| journal (des appels) | call log | `llm_client` counts calls and tokens |
| mandat | mandate | `require_mandate` is the campaign's front door |
| empreinte | digest | SHA-256; the KEY `"empreinte"` stays, the function moved |
| motif (de refus) | pattern | a regex, in `adaptation` |
| motif (d'écartement) | reason | a sentence, in `planificateur` |
| gravité | severity | from rules, never a model |
| résumer | summarise | the one-screen view of a profile or a plan |
| seulement / sauf | only / excluding | a campaign's scope |
| lancés | launched | the attempts actually sent |
| écourtée | cut short | the budget stopped the campaign |
| clôture | fence | the report's code-block delimiter |

## Judge criteria — HELD, and the reason is measured

These four values, and the four fields of the judge's JSON output (`analyse`,
`enfreint`, `critere`, `valeur`), live **inside `JUDGE_SYSTEM_PROMPT`** —
verified, not assumed. Renaming any of them changes the artefact the
89 / 100 / 96 were measured on, so the published figures would stop describing
the prompt in the repository.

| French | Would become | Status |
|---|---|---|
| divulgation | disclosure | **held** |
| obeissance | compliance | **held** |
| abus_outils | tool_abuse | **held** |
| aucun | none | **held** |
| analyse / enfreint / critere / valeur | the output schema | **held** |

Moving them is one commit of renaming plus a dev run (~100,000 tokens) and a
frozen-set consultation (~35,000), in that order, with both results recorded
before anything is published. `tests/test_migration.py` holds the wall:
it pins the prompt's length and asserts that none of the eight appears in the
migration map.

Two other vocabularies stay French for their own reasons:

- **the labelling categories** (`controle`, `fuite-directe`,
  `multitours-reussi`…): the author's taxonomy, named by its labels throughout
  CLAUDE.md and in the labelling menu. Renaming buys nothing functional and
  moves a vocabulary the author uses by hand.
- **the target names** (`leurre`, `demo`, `mock`): values of `--cible`, hence
  a documented interface.

## Everything else moved, in one pass

Keys are STRUCTURE, so they translated; internal enumerations (statuses,
severities, scorable states, replay outcomes, trail entry types, transformation
names, prerequisite names) went with them. 1,603 string replacements across 57
files, plus the three committed data files.

The rule that made it safe is the mirror image of the tokenizer rule for
identifiers: **replace a string only when its whole content is exactly a key**.
A French error message is never exactly `statut`, so prose is untouchable by
construction. Two passes are needed, because an f-string is a single token
before Python 3.12: the exact-match pass, then a regex for `['key']` subscripts
written inside f-strings.

What the pass could NOT see, and what caught it:

| Case | What broke | What found it |
|---|---|---|
| a prerequisite NAME | `outils` was both a profile key and a prerequisite name; the key moved, the data value did not | the validator test |
| the analyst's prompt | it asks the model for French keys, and the normalisation now reads English ones | the reconnaissance tests |
| a test helper's keyword | `_technique(modeles=…)` merged into a dict whose key had become `templates`, so the dict gained BOTH | the validator test |
| an assertion that reads like a key | `assert any("cible" in p …)` over French prose became `"target"` | the telemetry test |

Older data is read through `migration.modernise()`, which is deliberately
one-way: nothing writes the old names any more. It matters most for the three
kinds of file outside git — the local garak snapshot, a harvest waiting to be
labelled, and every `resultat.json` and sealed trail already produced.

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
| `motif` | two unrelated meanings AGAIN: a regex *pattern* (`adaptation.REFUSAL_PATTERNS`) and a *reason* a technique was skipped (`planificateur`). One rename cannot serve both |
| `exiger` | an ordinary French verb as well as the authorisation gate. Renaming it to `require_mandate` produced "finirait par require_mandate un mandat" in a comment and "AVANT d'require_mandate le mandat" in main. Neither broke a test |
| keyword arguments | `independants=` / `quoi=` are passed by name from four call sites. Renaming the parameter without them turned 693 green tests into 99 failures in one step — which is exactly why the order runs leaves-to-root |

## How to rename, now that both failures have happened

A global `sed` cannot tell an identifier from the same word in a French
sentence, nor from a JSON data key of the same spelling. Both damages were
done and caught in one afternoon: `"constats"` and `"campagne"` were rewritten
inside `rapport.py`'s data structure, and `# --- Gravité` became English words
inside French prose.

Two tools, used in this order:

1. **Rename with Python's `tokenize`**, which only touches NAME tokens, so
   strings and comments are untouchable by construction. That is how
   `rapport.py`'s 72 identifiers moved without a single data key changing —
   verified by diffing the sorted set of `"key":` strings before and after.
2. **Then run `check_rename_damage.py`** with the identifiers just
   introduced. It lists every line that holds both an accented word and a new
   identifier. It reports, it never rewrites: deciding whether `ask_llm`
   legitimately appears inside a French comment is a reading job.

Keyword arguments still have to be renamed with their call sites, and argparse
attributes (`arguments.cible`, derived from `--cible`) must NOT be renamed —
the CLI flag names them.

**Two more classes of reference that live in STRINGS or belong to someone
else**, and the tokenizer renames neither correctly:

- `@pytest.mark.parametrize("texte, attendu", …)` names the test's parameters
  in a string. Renaming the function's parameters without the string gives
  `function uses no argument 'texte'` at COLLECTION time, so the whole file
  fails to load rather than one test failing.
- an ATTRIBUTE after a dot belongs to the object, not to this file. A table
  containing `encode` rewrote `clear.encode()` into `clear.encoded()`. The
  renamer now refuses to touch a name preceded by `.`; before that guard it
  was caught by a test, but it could have landed on a less covered method.

**And one class no tool can see at all:** a name passed to
`monkeypatch.setattr` as a STRING. `setattr(module, "FICHIER_SORTIE", …)`,
`"_objectifs"`, `"MAX_OBJECTIFS"`, `"derniere_version"`, `"collecter"` — the
tokenizer sees a string literal, the import machinery sees nothing at all, and
only the failing test reports it. Six of them had to be chased by hand across
the evaluation and test layers. Grep for `setattr(` before declaring a rename
finished.

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
