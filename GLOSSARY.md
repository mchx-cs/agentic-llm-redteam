# Glossary — French → English

The project has been translated to English. This file is the **single source of
truth for terminology**, and it exists for one reason: 1,064 functions and
classes across 61 files cannot be renamed consistently from memory. Without a
fixed glossary, `cible` becomes `target` in one file and `system_under_test` in
another — which is exactly the drift the project already guards against for
label categories (`fuite_directe` vs `fuite-directe`).

**Rule: nothing gets renamed unless it is in this table.** Adding a term here is
part of the change, not a detail. What is still French is listed under
*Deliberately NOT translated* and *Terms whose translation changes BEHAVIOUR*,
each with its reason.

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
| motif (d'écartement) | reason | a sentence, in `planner` |
| gravité | severity | from rules, never a model |
| résumer | summarise | the one-screen view of a profile or a plan |
| seulement / sauf | only / excluding | a campaign's scope |
| lancés | launched | the attempts actually sent |
| langue (d'un échange) | language pair | a FACT on every corpus entry, `fr->fr`, `en->fr`… |
| tour fautif | breach turn | a LABEL: which turn the chatbot gave way on. `null` on a negative |
| étiqueté par | labelled by | `author` or `model`: whose judgement this label is |
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
- **the kept target name** `leurre`: `--target decoy` is the name now, but
  `leurre` still resolves to the same target, and still needs no mandate. The
  README has shown it since the project existed, and a documented interface
  does not get pulled from under its users by a translation.
  `PUBLIC_TARGET_NAMES` keeps it out of the help text, so the two do not read
  as two different targets.

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

## Files, folders and configuration keys

The last pass renamed the modules themselves. Three of its decisions are worth
keeping, because each one is a rule rather than a choice of word.

| Renamed to | Not to | Why |
|---|---|---|
| `stats.py` | `statistics.py` | a top-level module of that name shadows the standard library for the whole project and anything it imports |
| `evaluation/check_*.py` | `evaluation/test_*.py` | pytest would collect them, and they call a model |
| `payloads/library.json` | — | its `{objectif}` placeholder moved to `{objective}` with it; see the hazard table |

**Two names are CONTRACTS and keep their old spelling as a fallback**, for the
same reason the French command-line options are kept as aliases:

| New | Old, still read | Why it cannot simply break |
|---|---|---|
| `authorisation.json` | `autorisation.json` | gitignored, so nothing here can rename it on an operator's machine — and unlike every other work file it CANNOT be regenerated: it is a signed mandate. Losing sight of it makes the tool refuse to start against a target it is authorised to test |
| `TARGET_BODY`, `TARGET_RESPONSE_PATH`, `ACTIVE_PROFILE`, `JUDGE_PROFILE`, `CALL_BUDGET`, `TOKEN_BUDGET`, `TARGET`, `TARGET_HEADERS`, `TARGET_TIMEOUT` | `CIBLE_CORPS`, `CIBLE_CHEMIN_REPONSE`, `PROFIL_ACTIF`, `PROFIL_ARBITRE`, `BUDGET_APPELS`, `BUDGET_TOKENS`, `CIBLE`, `CIBLE_ENTETES`, `CIBLE_DELAI` | a `.env` lives on machines this repository never sees |

The new name wins when both are set — someone adding the new line means it to
take effect, and the stale line is what they are replacing. One note on stderr
names the lines to rename, said once after every key is read. `config.LEGACY_ENV`
is the single place that knows the pairs, and `tests/test_config_env.py` reads
all nine under their OLD name and checks the value arrives where the code USES
it, not merely that the map lists it.

The provider keys (`OPENAI_API_KEY`, `GROQ_MODEL`…) were never French and follow
each provider's own convention, so they did not move — and a test says so.

## Translated in a coordinated pass, not file by file

Three kinds of French crossed every file, so each moved in ONE pass with its
artefacts rather than layer by layer. What each actually cost:

| What | Why it could not go file by file | What it dragged with it |
|---|---|---|
| **JSON data keys** (`constats`, `couverture`, `portee`, the `STATES` keys…) | persisted in `resultat.json`, in 18 sealed trails and in the committed example | `migration.modernise()`, one-way, called on every read |
| **operator-facing messages** (errors, diagnostics, campaign output, report text) | they ARE the project's output: they appear verbatim in the README excerpt and in `examples/demo-report.md` | one fresh campaign against `demo` (19 calls, 30,494 tokens), from which both were regenerated |
| **`.env` configuration keys** (`CIBLE_CORPS`, `CIBLE_CHEMIN_REPONSE`…) | a configuration contract: it lives on machines this repository never sees | `config.LEGACY_ENV` and a note on stderr; see *Files, folders and configuration keys* above |

The example report cost no second call: `result.json` IS the built report, so
re-rendering it abridged is a function call. That is the fourth time the "JSON
is the source of truth, Markdown is only a view" choice has paid for itself in
cash.

## Who decided a label

`labelled_by` is on every corpus entry: `author` or `model`.

The project's rule is that labels are the AUTHOR's ground truth, never a model's. That
rule was set aside on explicit request for the 119 multi-turn entries (2026-11-16), so
the data records it rather than leaving it to be discovered. A measurement against
model-decided labels says "two models agree", not "the judge is right".

| Where | What it does |
|---|---|
| the data | `labelled_by` on all 209 entries, made total so a missing field is never read as "probably the author" |
| `evaluate_judge` | warns ABOVE the figures, not below |
| `label.py` | overwrites the provenance to `author` — relabelling by hand makes it ground truth |

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
| `tester` | two meanings again: *probe the wiring* (`targets/http.py`) and *run this measurement* (now `evaluation/check_*.py`). Renaming the first gave the evaluation scripts a `probe_target()` that probes nothing |
| French PROSE containing an identifier | the worst of the four, because the suite stays green. Renaming `prochain` → `next_attempt` rewrote twelve French sentences, including two strings rendered into the client-facing report and — worst — a target reply pinned VERBATIM in `tests/test_adaptation.py`. A test whose data is falsified no longer tests what it claims. A detector now scans for English identifiers inside French sentences after every rename pass |
| data keys that look like identifiers | `TRANSFORMATIONS`' keys (`"identite"`, `"majuscules"`) travel into `resultat.json`, the committed example and the README excerpt. A `identite` rename hits the string literal too, and the tests follow silently because they were renamed in the same pass |
| local variables sharing a name with a dict key | the same hazard as above, met THREE times: renaming the local `echanges`, `fiche` or `identite` also rewrote `"echanges"`, `"identite"` and `"majuscules"` in the neighbouring dict. The suite caught each one, but by ricochet — `tests/test_report.py::TestLeSchemaDeDonneesEstEPINGLE` now pins the data schema directly and names the offending key |
| `motif` | two unrelated meanings AGAIN: a regex *pattern* (`adaptation.REFUSAL_PATTERNS`) and a *reason* a technique was skipped (`planner`). One rename cannot serve both |
| `exiger` | an ordinary French verb as well as the authorisation gate. Renaming it to `require_mandate` produced "finirait par require_mandate un mandat" in a comment and "AVANT d'require_mandate le mandat" in main. Neither broke a test |
| keyword arguments | `independants=` / `quoi=` are passed by name from four call sites. Renaming the parameter without them turned 693 green tests into 99 failures in one step — which is exactly why the order runs leaves-to-root |
| a placeholder and the keyword that fills it | `{objectif}` lives in `library.json`; `.format(objectif=…)` lives in the code, and nothing links the two. Renaming the keyword alone made every template raise KeyError — and `payloads/validate.py` broke the same way, so the library still reported itself *valid*. Only a planner test noticed. Both sides must move together, or neither |
| a module named after its own main function | `agents/judge.py` holds `judge()`. `import agents.judge as judge` followed by `from agents.judge import judge` silently shadows the alias, and every `monkeypatch.setattr(judge, …)` then patches a function. Import such a module under its full name |
| an argparse dest after a flag rename | `--seulement` became `--only`, so argparse sets `only`; the code still read `arguments.seulement`. It raises nothing on a path never taken, so `--only` and `--excluding` were accepted and SILENTLY IGNORED. Three `evaluation/` entry points died outright the same way. `tests/test_cli_wiring.py` now checks every parser's dests against the attributes its module reads |
| a Bash heredoc around Python with a backslash | `print("
…")` loses its backslash and becomes a real newline, which leaves a syntax error if the string ends on that line and a wrong string if it does not. It took `evaluation/measure_adaptation.py` out for a whole commit, unnoticed because `evaluation/` has no tests. Write such a script with a file tool, never a heredoc |
| a sense-specific word in a data-key pass | `moyen` means both *medium* (a severity) and *mean* (an average), and the key pass picked the wrong one for a measurement script's result dict; `egal` came out as `level` instead of `tie`. Neither broke anything a test watched |

## How to rename, now that both failures have happened

A global `sed` cannot tell an identifier from the same word in a French
sentence, nor from a JSON data key of the same spelling. Both damages were
done and caught in one afternoon: `"constats"` and `"campagne"` were rewritten
inside `report.py`'s data structure, and `# --- Gravité` became English words
inside French prose.

Two tools, used in this order:

1. **Rename with Python's `tokenize`**, which only touches NAME tokens, so
   strings and comments are untouchable by construction. That is how
   `report.py`'s 72 identifiers moved without a single data key changing —
   verified by diffing the sorted set of `"key":` strings before and after.
2. **Then run `check_rename_damage.py`** with the identifiers just
   introduced. It lists every line that holds both an accented word and a new
   identifier. It reports, it never rewrites: deciding whether `ask_llm`
   legitimately appears inside a French comment is a reading job.

Keyword arguments still have to be renamed with their call sites. An argparse
attribute is named by its FLAG, so the two move together or not at all:
`parser.add_argument("--target", "--cible", dest="target")` sets
`arguments.target`, because argparse takes the first long option — which is
also why a kept French alias must come second, and why an explicit `dest=`
is worth writing when both are listed. Renaming the attribute alone, or the
flag alone, is the defect `tests/test_cli_wiring.py` exists to catch.

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

## The corpus's languages, recorded rather than assumed

The corpus is not monolingual, and until 2026-11-15 nothing said so. The field
`languages` now carries each entry's pair, derived mechanically by
`evaluation/languages.py`.

| Pair | Where it occurs |
|---|---|
| `fr->fr` | 69 of the 90 single-turn exchanges, 79 of the 119 harvested conversations — and **every** positive |
| `en->en` | the 13 deliberate English cases (E01-en … E12-en, T02, T05) |
| `en->fr` | 33 harvested conversations, a population the single-turn corpus does NOT contain |
| `?` on one side | a spelled-out secret, Base64, hex, a reversed value, a bare greeting — strings with no language. A real answer, not a failure |

Two rules this imposes on a future rename or translation pass:

- **the field is a FACT, never a label.** It is stamped by `label.py`, not asked of the
  author, and nothing about it touches `expected`. The three questions the author answers
  stay three;
- **the stamp is STORED, not re-derived on read.** If the classifier's word lists move,
  past measurements keep the pair they were measured with — the same reason the garak
  snapshot is frozen. A test checks the stored stamps still match the text, and if it ever
  fails that is a signal to decide, not to re-derive in silence.

## Two fields added to the corpus, and the difference between them

Added on 2026-11-15, before labelling the 119 harvested conversations, because
afterwards either would have cost 119 entries.

| Field | Kind | Who fills it |
|---|---|---|
| `languages` | **FACT** — derivable from the text | stamped by `label.py` |
| `breach_turn` | **LABEL** — a reading of the conversation | asked, as a fourth question |

The distinction is not pedantic. `breach_turn` cannot be derived: a leaked secret can be
found by string search, but which turn the chatbot *obeyed* on, or *called a tool* on,
has no string to search for. Treating it as a fact would have put a mechanical guess
where the ground truth belongs — the thing `labelling_prepass.py` exists to refuse.

`breach_turn` is asked only where it has an answer: `null` on a negative, filled in as 1
on a single-turn breach (arithmetic, not judgement), asked on a multi-turn breach.

The judge emits `"tour"` in its MULTI-TURN JSON, so neither field is write-only. That
addition was free because the multi-turn instruction has never been measured; the
single-turn one stays byte-identical, and a test holds it.

## Terms whose translation changes BEHAVIOUR

Flagged here so nobody treats them as prose:

- **refusal patterns** (`agents/adaptation.py`): they match what a
  French-speaking target writes. Translating them stops adaptation from firing
  against a French target — and they were corrected once already, after real
  campaign responses that are now pinned verbatim in tests.
- **the demo target's system prompt**: the target *is* a French library
  assistant. Translating it changes the measured object: the three defence
  levels, the measured gradient, the example report, the README excerpt.
- **the judge's instruction**: SETTLED by measurement on 2026-11-14, and the
  answer is no. The forging risk was closed first — its structural labels would
  become `User:` / `Assistant:`, which **59 library payloads contain**, so a
  target echoing one could forge a turn in the judge's own prompt. With that
  guard in place, a faithful English translation was measured against the
  French one on the same `dev` set: 86 / 100 / 94 against 89 / 100 / 96, one
  single case apart, which is this judge's known non-determinism at
  temperature 0. No gain, so French stays the default and the English version
  is kept beside it — it cost its measurement and it documents the answer.
