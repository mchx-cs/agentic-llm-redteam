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

## Deliberately NOT translated

| What | Why |
|---|---|
| the 91 commit messages | public history; rewriting it would rewrite every hash |
| the 18 sealed audit trails | a seal whose content changes is no longer a seal |
| recorded exchanges in the corpus | a target's actual words are **evidence**. Translating a recorded response fabricates data that no target ever produced |
| OWASP family labels (`LLM01:2025 …`) | they are the standard's own strings |
| garak probe names and tags | they come from upstream |

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
