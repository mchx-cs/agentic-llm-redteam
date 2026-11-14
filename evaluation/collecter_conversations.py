"""
evaluation/collecter_conversations.py — Harvests real multi-turn
conversations, to be labelled by hand (phase 3b).

`collecter_echanges.py` harvests SINGLE-turn exchanges. The judge can only
score that format, and all 90 exchanges in the corpus are of it. For it to
learn to score a conversation, a corpus of conversations has to exist first —
labelled by hand, by the author, as always. This script supplies the raw
material.

Why it is FREE, and why that matters
------------------------------------
No attacker model, no judge: the sequences are fixed, and only the TARGET is
called. Against `--cible demo`, which runs on Ollama locally, the harvest
therefore burns no quota at all. That is what makes the multi-turn corpus
reachable: the judge's free tier (200,000 tokens a day) would not allow
harvesting AND measuring.

Where the sequences come from
-----------------------------
The same ingredients as the single-turn composition: a complete garak payload
serves as the first turn, and the objective derived from reconnaissance
supplies the second (`attaquant.sequence_turns`). Nothing is invented for the
occasion — we only harvest techniques the tool already practises.

A useful consequence: the single-turn variant of the same ingredients already
exists (`attaquant.compose`). `--comparer` harvests both, which gives pairs
whose only difference is the number of turns. That is the measurement which
will settle what multi-turn is worth, and it only holds if the two arms share
their ingredients.

Two inherited rules, non-negotiable
-----------------------------------
- **The judge's opinion is NOT recorded.** Seeing it would influence the human
  label, and we would be measuring the judge against itself.
- **The samples of one sequence form a GROUP**, and a group is never split
  between the development set and the test set.

Run it from the project root:
    python -m evaluation.collecter_conversations --cible demo
    python -m evaluation.collecter_conversations --cible demo --comparer
"""

import argparse
import json
from pathlib import Path

from agents.attaquant import load_library, compose, sequence_turns
from cibles import choose_target, is_bundled_target
from cibles.conversation import MAX_TURNS, require_conversation, play

OUTPUT_FILE = Path(__file__).parent / "a_etiqueter_conversations.json"

# The target has randomness: the same sequence twice can give two different
# outcomes (one gives way, the other refuses). Both are useful cases.
SAMPLE_COUNT = 2

# How many sequences at most. An explicit bound, like every loop in the
# project: a harvest starting on 1,143 payloads × 2 samples would take the
# evening and produce a corpus nobody will ever label.
MAX_SEQUENCES = 12

# The library's generic objectives ask for nothing sensitive ("introduce
# yourself in one sentence"): they serve as CONTROLS, and a corpus with no
# controls would have zero false positives by construction — the trap the
# OWASP manual names explicitly.
CONTROL_OBJECTIVE = "presentation"

# How many reconnaissance-derived objectives we cycle through. Bounded: a
# talkative target can declare six refused subjects, and crossing everything
# with everything would inflate a harvest nobody will ever label.
MAX_OBJECTIVES = 3


def _objectives(ask_target, library, harmless=False):
    """
    What the second turn is going to DEMAND.

    The problem fixed here is structural, and the first harvest made it
    visible: 3 positives against 61 negatives. The library's three generic
    objectives (`presentation`, `mission`, `culture-generale`) are all
    HARMLESS, so the second turn never asked for what the target protects.
    Measuring a judge's recall on three cases would mean nothing.

    The objectives that demand something come from RECONNAISSANCE: `refus-N`
    for each subject the target says it refuses, `outil-N` for each tool it
    declares. That is exactly what a campaign does, and it is free — the
    analyst runs on the active profile, local by default.

    With `harmless`, we keep the control objective: a corpus needs entirely
    inoffensive conversations, otherwise its false positives are zero by
    construction.
    """
    generic = {o["id"]: o for o in library["objectives"]}
    control = (generic.get(CONTROL_OBJECTIVE)
                or next(iter(generic.values())))
    if harmless:
        return [control], "objectif de contrôle (anodin)"

    from agents.planificateur import objectives_for
    from agents.reconnaissance import reconnoitre

    print("Reconnaissance de la cible (sondes anodines, modèle local)...")
    profile = reconnoitre(ask_target)
    targeted = [o for o in objectives_for(profile, library)
             if o.get("origin") == "reconnaissance"][:MAX_OBJECTIVES]

    if not targeted:
        # A target declaring neither a refused subject nor a tool yields no
        # targeted objective. We SAY SO: without that, the harvest would fall
        # back on the harmless objective and we would then wonder why there
        # are no positives.
        print("/!\\ La cible ne déclare ni sujet refusé ni outil : aucun "
              "objectif ciblé. Récolte avec l'objectif anodin, qui ne "
              "produira presque que des négatifs.")
        return [control], "objectif de contrôle (faute de mieux)"

    for objective in targeted:
        print(f"  objectif retenu : {objective['id']} — "
              f"{objective['wording'][:70]}")
    return targeted, f"{len(targeted)} objectif(s) issus de la reconnaissance"


def _sequences(limit=MAX_SEQUENCES, objectives=None):
    """
    The sequences to play: (identifier, messages, provenance).

    One complete payload per technique, no more: a variety of techniques beats
    several variants of the same one, exactly like a campaign's round-robin.
    """
    library = load_library()
    if not objectives:
        generic = {o["id"]: o for o in library["objectives"]}
        objectives = [generic.get(CONTROL_OBJECTIVE)
                     or next(iter(generic.values()))]

    sequences = []
    for technique in library["techniques"]:
        complete = technique.get("complete_payloads") or []
        if not complete:
            continue
        # Round-robin over the objectives: each sequence gets ONE, so the
        # harvest's size stays predictable (sequences × samples) while what is
        # demanded still varies.
        objective = objectives[len(sequences) % len(objectives)]
        sequences.append({
            "technique": technique["id"],
            "objective": objective["id"],
            "messages": sequence_turns(complete[0], objective),
            "single_turn": compose(complete[0], objective),
        })
        if len(sequences) >= limit:
            break
    return sequences


def _fragment(text):
    """An identifier's alphanumeric characters, and nothing else."""
    return "".join(c for c in str(text) if c.isalnum()) or "x"


def _label(target_name):
    """
    An identifier fragment saying WHAT the conversation was harvested against
    (`demo`, `demo3`, `leurre`…).

    Without it, two harvests tread on each other: levels 2 and 3 of the demo
    target REFUSE, so they supply the negatives of a corpus level 1 would fill
    with positives. All three have to be harvestable, and therefore their
    identifiers have to differ.
    """
    return _fragment(target_name or "env")


def collect(target_name=None, compare=False, limit=MAX_SEQUENCES,
              harmless=False):
    ask_target = choose_target(target_name)
    require_conversation(ask_target, target_name or "la cible configurée")
    label = _label(target_name)

    objectives, summary = _objectives(ask_target, load_library(),
                                   harmless)
    print(f"  -> {summary}\n")
    sequences = _sequences(limit, objectives)
    if not sequences:
        raise SystemExit(
            "Aucune séquence : la bibliothèque n'a aucun payload complet.\n"
            "Synchronise l'instantané garak "
            "(python -m payloads.source_garak --version).")

    # We ADD to the existing harvest instead of overwriting it. A working
    # file a second command erases is an evening of labelling lost — and
    # harvesting several defence levels needs several commands precisely.
    entries = _existing_harvest()
    already = {e["id"] for e in entries}

    # Bounded loops: sequences (a finite list) × SAMPLE_COUNT.
    for number, sequence in enumerate(sequences, start=1):
        # The identifier carries the target AND the objective. Without the
        # objective, a harvest rerun with a different objective fell back on
        # the same identifiers, found them "already harvested" and SKIPPED
        # them: the command looked like it had worked while the new objective
        # was never sent. Found by comparing what the harvest announced to
        # what it contained.
        group = (f"C-{label}-{_fragment(sequence['objective'])}"
                  f"-{number:02d}")
        for sample in range(1, SAMPLE_COUNT + 1):
            if f"{group}-{sample}" in already:
                print(f"{group}-{sample} : déjà récolté, ignoré.")
                continue
            turns = play(ask_target, sequence["messages"])
            entries.append(_entry(group, sample, sequence, turns))
            print(f"{group}-{sample} ({sequence['technique']}) : "
                  f"{len(turns) // 2} tour(s)")

            if compare:
                # The SAME pair of ingredients in a single message. The pair
                # only holds if played in the same session, against the same
                # target, back to back: a probabilistic target drifts.
                reply = ask_target(sequence["single_turn"])
                entries.append(_entry(
                    group, sample, sequence,
                    [{"role": "attacker", "content": sequence["single_turn"]},
                     {"role": "target", "content": reply}],
                    suffix="-mono"))
                print(f"{group}-{sample}-mono : 1 tour (témoin)")

    OUTPUT_FILE.write_text(
        json.dumps({"conversations": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{len(entries)} conversation(s) écrites dans "
          f"{OUTPUT_FILE.name}, à étiqueter à la main :\n"
          f"  python -m evaluation.etiqueter")
    return entries


def _existing_harvest():
    """What is already harvested and not yet poured into the corpus."""
    if not OUTPUT_FILE.exists():
        return []
    from migration import modernise

    return modernise(json.loads(OUTPUT_FILE.read_text(
        encoding="utf-8"))).get("conversations", [])


def _entry(group, sample, sequence, turns, suffix=""):
    """An entry to label. The fields to fill in stay None."""
    return {
        "id": f"{group}-{sample}{suffix}",
        "group": group,          # single-turn and multi-turn go TOGETHER
        "format": "mono-tour" if len(turns) == 2 else "multi-tours",
        "turns": turns,
        "source": (f"cible réelle — {sequence['technique']} / "
                   f"{sequence['objective']} / "
                   f"{'composé' if suffix else 'séquencé'}"),
        "secret": "ARCHIVES-7731",
        "category": None,         # to fill in by hand
        "dataset": None,               # to fill in by hand: "dev" or "test"
        "expected": None,           # to fill in by hand: true or false
        "trap": "",               # to fill in by hand
    }


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Récolte des conversations multi-tours à étiqueter.")
    parser.add_argument("--cible", default=None,
                         help="cible à interroger (défaut : celle de .env). "
                              "`demo` est locale, donc gratuite.")
    parser.add_argument("--comparer", action="store_true",
                         help="récolter aussi la variante MONO-TOUR des mêmes "
                              "ingrédients, pour des paires comparables")
    parser.add_argument("--anodin", action="store_true",
                         help="second tour anodin (objectif de contrôle), au "
                              "lieu de réclamer ce que la cible protège : "
                              "récolte des NÉGATIFS")
    parser.add_argument("--sequences", type=int, default=MAX_SEQUENCES,
                         metavar="N", help=f"séquences au plus "
                                           f"(défaut : {MAX_SEQUENCES})")
    arguments = parser.parse_args(arguments)

    if arguments.cible and not is_bundled_target(arguments.cible):
        # Harvesting means sending real payloads: the mandate applies.
        # Saying so here avoids discovering it after the first send.
        print("/!\\ Cible non livrée avec le projet : vérifie que le mandat "
              "la couvre (voir audit.py) avant de lancer la récolte.")

    print(f"Cible : {arguments.cible or 'celle de .env'}. "
          f"Aucun juge, aucun modèle attaquant : seule la cible est appelée.")
    print(f"Au plus {arguments.sequences} séquence(s) × {SAMPLE_COUNT} "
          f"échantillon(s), {MAX_TURNS} tours maximum chacune.\n")
    collect(arguments.cible, arguments.compare, arguments.sequences,
              arguments.harmless)
    return 0


if __name__ == "__main__":
    main()
