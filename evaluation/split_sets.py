"""
evaluation/split_sets.py — Which group goes to `dev` and which to `test`.

A SAMPLING DESIGN decision, not ground truth. It needs no verdict: assigning
a group to a set does not require knowing whether its exchanges are
vulnerabilities. The verdicts, the categories and the breach turns stay the
author's, and nothing here touches them.

WHY IT IS DECIDED BEFORE LABELLING, AND NOT DURING. `label.py` asks for the
set as one of its questions, which means the set gets chosen just after the
verdict has been read — and that is a bias: a hard case is exactly the one you
are tempted to keep in `dev`, where you are allowed to tune against it.
Assigning the set from the group's STRUCTURE, before any verdict has been
seen, removes that temptation entirely. The tool then says "Set: dev (imposed
by group X)" and does not ask.

THE RULES, in order of precedence:

1. **A group is never split.** One payload and its samples travel together,
   or the frozen set would hold a rewording of a case the judge was tuned on.
   This is enforced elsewhere too — `label.py --check`, `integrate()` and
   `load_exchanges()` all refuse a split group.

2. **Hand-written cases go to `dev`.** Precedent, and a reason: D13–D20 all
   went to `dev` because a case written to expose a specific trap is a case
   you need to be ALLOWED to tune against. In the frozen set it would be
   unusable for the job it exists for.

2b. **A declared FROZEN LOT goes to `test`**, which is the same rule read
   backwards rather than an exception to it. `evaluation/frozen_lot.py` is
   written to be held out — never looked at while a criterion is adjusted,
   consulted afterwards as a check — so its groups are imposed `test` and the
   striping never touches them either.

   The two impositions are opposite and both absolute, because what decides is
   the declared INTENT and not the text: a twin pair written to settle where a
   criterion's edge falls belongs in `dev`, and a twin pair written to measure
   whether that edge generalises belongs in `test`. Nothing in the cases
   themselves tells them apart, which is why each lot declares what it is for.

3. **Stratify on the axes that are genuinely different populations**, so that
   neither set is a skewed sample:
   - the defence LEVEL (`demo`, `demo:2`, `demo:3`). The project already
     refuses to pool targets of different resistances in one test;
   - the LANGUAGE family (a French attacker, or garak's English one). A
     population established on 2026-11-15, absent from the single-turn
     corpus.

4. **Roughly a quarter of the groups to `test`**, matching the existing
   corpus's 23 / 90.

WHAT THIS CANNOT DO, and it has to be said: it does not stratify on the
POSITIVES, because the labels do not exist yet. The mechanical facts give a
LOWER bound — 10 entries where the secret string appears in a chatbot turn —
and an `obeissance` or `abus_outils` breach leaves no string to count. So the
split is balanced on structure, and the positives fall where they fall. The
assignment prints how many mechanical positives each set receives, so a
badly skewed draw is visible before any labelling is done rather than after.

DETERMINISTIC. No randomness at all: the groups of a stratum are sorted by
name and every fourth one goes to `test`. Two runs give the same split, and
the split can be re-derived from the data alone — the same requirement as the
garak snapshot, for the same reason.
"""

import argparse
import json
import re
from pathlib import Path

HARVEST = Path(__file__).parent / "to_label_conversations.json"

# One group in this many goes to the frozen set.
ONE_IN = 4

TEST = "test"
DEV = "dev"


def handwritten_groups():
    """
    The groups of the hand-written stratum, READ from the module that declares
    them.

    Keyed to the prefix `A-` until 2026-11-18, when the criterion-4 cases
    arrived grouped `T-…` and fell into "other" — so `label.py` would have
    ASKED for their set and the striping could have sent the T01/T02 twins
    into the FROZEN set. That is the defect recorded on 2026-11-16, and a pair
    written to pin one specific trap is unusable there for the only job it
    exists for.

    A prefix is a convention the next person breaks, and three days was
    enough. Reading the declaration instead means any new hand-written group
    is recognised whatever letter it starts with — the same reason
    `judge_identity()`, `stats.STATES` and the attack catalogue are read
    rather than restated.

    The import is LAZY and failure is non-fatal: this module is also used on
    corpora that predate the hand-written cases, and a split must not depend
    on a sibling module importing cleanly.
    """
    try:
        from evaluation.handwritten_conversations import CASES
    except Exception:
        return frozenset()
    return frozenset(group for _, group, _, _ in CASES)


def frozen_groups():
    """
    The groups of the DECLARED frozen lot, read from the module that declares
    them — the mirror of `handwritten_groups`, and for the opposite reason.

    Same lazy, non-fatal import: a split must not depend on a sibling module
    importing cleanly, and this module is also used on corpora that predate
    the lot.
    """
    try:
        from evaluation.frozen_lot import CASES
    except Exception:
        return frozenset()
    return frozenset(group for _, group, _, _ in CASES)


def defence_level(group):
    """
    The target the group was harvested against, read from its name.

    `C-demo-04` and `C-demo-refus1-04` are both level 1 — the middle part is
    the OBJECTIVE, not the target. `C-demo2-04` is level 2. Getting this
    wrong would put three different resistances in one stratum.

    A hand-written group is its own stratum, and always `dev`: see
    `handwritten_groups` for why that is read rather than spelled out.
    """
    # Declared OR conventional, and both rather than a choice between them.
    # The declaration protects exactly what the module ships -- including the
    # `T-` groups whose prefix nobody had foreseen. The `A-` convention
    # protects anyone who follows it from somewhere else, which is what the
    # rule did before and what no declaration can cover. Dropping either one
    # loses a case the other does not catch.
    if group in handwritten_groups() or group.startswith("A-"):
        return "hand-written"
    # Declared only: there is deliberately NO prefix convention here. `A-`
    # earned one by predating the declaration; a new lot has no such history,
    # and a second convention would be a second thing to break.
    if group in frozen_groups():
        return "frozen-lot"
    match = re.match(r"C-demo(\d?)", group)
    return f"demo{match.group(1) or '1'}" if match else "other"


def imposed_set(group):
    """
    The set a group's STRUCTURE imposes, or None when the striping decides.

    THE ONE PLACE. The two impositions are opposite -- hand-written cases to
    `dev`, a declared frozen lot to `test` -- and both are absolute, so a
    caller that re-implemented either would be a second source of truth for a
    rule whose whole point is that nobody gets to answer it.

    `label.py` asked the question while this module held the rule, and nothing
    connected them until 2026-11-18: a human answering "test" put the rule
    straight back. Pinning that junction by reading `label.py`'s source for a
    string then failed to catch the branch being disabled, which is why the
    decision lives here and is called rather than copied.
    """
    level = defence_level(group)
    if level == "hand-written":
        return DEV
    if level == "frozen-lot":
        return TEST
    return None


def attacker_language(entries):
    """
    `fr` or `en`, from the pair already recorded on each entry.

    Taken from the group as a whole: four samples of one payload share their
    attacker, so a disagreement would mean the recorded pairs are wrong rather
    than the group being mixed.
    """
    languages = {e.get("languages", "?->?").split("->")[0] for e in entries}
    if languages == {"en"}:
        return "en"
    if languages == {"fr"}:
        return "fr"
    return "mixed"


def stratum(group, entries):
    return f"{defence_level(group)}/{attacker_language(entries)}"


def assign(groups):
    """
    group name -> "dev" or "test".

    `groups` maps a group name to its entries. Deterministic: within a
    stratum, groups are sorted by name and every ONE_IN-th goes to `test`.
    Starting at index 1 rather than 0 means a stratum of one or two groups
    keeps them ALL in `dev` — with so few, sending one to the frozen set
    would leave `dev` with no example of that population at all, and `dev` is
    the set that has to cover everything.
    """
    decision = {}
    strata = {}
    for name, entries in groups.items():
        # Rule 2 is ABSOLUTE and comes before the striping. A first version
        # let the every-fourth rule run over the hand-written stratum too, and
        # it sent `A-confirmation` — the A03/A04 twins, written to pin one
        # specific trap — into the frozen set, where they would be unusable
        # for the only job they exist for.
        # Both impositions, from the one place that states them. They come
        # BEFORE the striping and are absolute: a hand-written case needs to
        # be tunable against, and a lot written to be held out has nothing to
        # gain from the striping and everything to lose if a quarter of it
        # landed in `dev` -- the criterion would then be tuned against a case
        # written to measure it.
        imposed = imposed_set(name)
        if imposed is not None:
            decision[name] = imposed
            continue
        strata.setdefault(stratum(name, entries), []).append(name)

    for names in strata.values():
        for position, name in enumerate(sorted(names)):
            decision[name] = (TEST if position % ONE_IN == 1 else DEV)
    return decision


def _groups(entries):
    groups = {}
    for entry in entries:
        groups.setdefault(entry["group"], []).append(entry)
    return groups


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Assign each group to dev or test, deterministically.")
    parser.add_argument("--harvest", default=str(HARVEST),
                        help="the harvest to read")
    parser.add_argument("--write", action="store_true",
                        help="write the assignment into the harvest. Without "
                             "it, nothing is modified and the plan is only "
                             "printed.")
    arguments = parser.parse_args(arguments)

    from migration import modernise
    from evaluation.labelling_prepass import facts

    path = Path(arguments.harvest)
    data = modernise(json.loads(path.read_text(encoding="utf-8")))
    entries = data["conversations"]
    groups = _groups(entries)
    decision = assign(groups)

    print(f"{len(groups)} group(s), {len(entries)} entr(y/ies).\n")
    print(f"{'group':20s} {'stratum':20s} {'n':>2} {'pos':>3}  set")
    print("-" * 56)
    for name in sorted(groups):
        members = groups[name]
        positives = sum(1 for e in members if facts(e)["secret_par_la_cible"])
        print(f"{name:20s} {stratum(name, members):20s} {len(members):>2} "
              f"{positives:>3}  {decision[name]}")

    for which in (DEV, TEST):
        chosen = [n for n, s in decision.items() if s == which]
        n_entries = sum(len(groups[n]) for n in chosen)
        positives = sum(1 for n in chosen for e in groups[n]
                        if facts(e)["secret_par_la_cible"])
        print(f"\n{which:4s}: {len(chosen):>2} group(s), {n_entries:>3} "
              f"entr(y/ies), {positives} mechanical positive(s)")

    print("\nThe positives above are a LOWER bound: an `obeissance` or "
          "`abus_outils` breach\nleaves no string to count. The split is "
          "balanced on structure, not on labels.")

    if not arguments.write:
        print("\nNothing written. Re-run with --write to apply it.")
        return 0

    for entry in entries:
        entry["dataset"] = decision[entry["group"]]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"\nWritten into {path.name}. `label.py` will now say "
          f'"Set: … (imposed by group …)" instead of asking.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
