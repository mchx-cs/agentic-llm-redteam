"""
evaluation/measure_adaptation_real.py — Does adaptation win against a REAL
target?

`measure_adaptation.py` already answers that question, but on SIMULATED
targets whose giving-way techniques we decree. Here the target is a real
badly protected model (`--cible demo`), with real payloads and real
probabilistic replies.

WHY A LOCAL JUDGE. Measured on 2026-11-12: a campaign costs ~13,000 tokens
per attempt with the Groq judge, i.e. ~520,000 tokens for a single pair at
budget 20 — 2.6 days of the free quota. And one pair would conclude nothing,
the target being probabilistic: five to ten would be needed, hence weeks.
With a local judge the measurement is free, so repeatable as often as needed.

THE BIAS, AND HOW TO READ IT. llama3.2 as a judge caps at 50% recall: it
misses one vulnerability in two. This bias is NOT symmetric between the two
arms, and that is the point — adaptation feeds on the VERDICTS
(`technique_efficace` moves up what has just worked), while the static arm
follows its plan listening to nothing.

**A correction made after the 40 pairs of 2026-11-12:** this note used to say
that a poor judge DEPRIVES adaptation of signal, hence that the measurement
underestimates its gain. That is incomplete, and the error matters. A judge
that misses a vulnerability does not stay silent: it returns a NEGATIVE
verdict, which adaptation reads as `technique_bloquee` and which steers it
away from a technique that was working. It does not starve adaptation, it
MISINFORMS it. The bias can therefore make the adaptive arm actively worse
than the control, and not merely worse than it really is.

Consequence for reading a result:
- if the adaptive arm wins despite that handicap, it is a LOWER BOUND on the
  real gain, and the result is solid;
- if it loses or draws, NOTHING can be concluded about adaptation — only that
  the pair {adaptation + this judge} is not worth the static plan. Which is
  useful to know, but does not answer the question asked.

Run it from the project root, with JUDGE_PROFILE=local:
    python -m evaluation.measure_adaptation_real --paires 3 --budget 8
"""

import argparse
import contextlib
import io
import json
import os
import tempfile
import time
from pathlib import Path

# Both arms must see exactly the same target and the same pool: only
# `adaptive` changes. Everything else is held constant by construction.
TARGET = "demo"


def _campaign(adaptive, budget):
    """A whole campaign, with no noise on standard output."""
    import main
    from targets import choose_target

    initial_budget = main.MAX_ESSAIS
    main.MAX_ESSAIS = budget
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return main.run_campaign(choose_target(TARGET), TARGET,
                                        adaptive=adaptive)
    finally:
        main.MAX_ESSAIS = initial_budget


def _measures(result):
    """What we keep from a campaign: findings AND coverage."""
    import stats

    states = result.get("states") or []
    rate = stats.success_rate(states)
    return {
        "findings": len(result.get("findings") or []),
        "attempts": len(result.get("launched") or []),
        "scorable": rate["scorable"],
        "non_scorable": rate["non_scorable"],
        # Coverage counts as much as findings: an arm that finds more while
        # touching one family only is not necessarily better.
        "modules": len({e.get("group") or e["technique"]
                        for e in result.get("launched") or []}),
        "familles": len({e["owasp_family"] for e in
                         result.get("launched") or [] if e["owasp_family"]}),
    }


def one_pair(budget, show=print):
    """Both arms, back to back, on the same target."""
    pair = {}
    for arm, adaptive in (("adaptive", True), ("static", False)):
        start = time.monotonic()
        result = _campaign(adaptive, budget)
        pair[arm] = {**_measures(result),
                       "seconds": round(time.monotonic() - start, 1)}
        m = pair[arm]
        show(f"    {arm:10s} {m['findings']} constat(s), "
                 f"{m['modules']} module(s), "
                 f"{m['non_scorable']} non scorable(s), {m['seconds']} s")
    return pair


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Adaptive against static plan, on the real demo "
                    "target.")
    parser.add_argument("--pairs", "--paires", type=int, default=3,
                        dest="pairs",
                        help="number of pairs to run (default: 3)")
    parser.add_argument("--budget", type=int, default=8,
                        help="attempts per campaign (default: 8)")
    parser.add_argument("--output", "--sortie", default=None, dest="output",
                        metavar="FILE",
                        help="where to write the results as they come")
    arguments = parser.parse_args(arguments)

    from config import JUDGE_PROFILE
    print(f"Juge : {JUDGE_PROFILE}. Cible : {TARGET}. "
          f"{arguments.pairs} paire(s) × {arguments.budget} essais.")
    if JUDGE_PROFILE != "local":
        print("/!\\ Juge NON local : cette mesure va consommer du quota. "
              "Lance-la avec JUDGE_PROFILE=local.")
    print()

    output = Path(arguments.output) if arguments.output else None
    pairs = []
    # A bounded loop, as everywhere: the number of pairs is an argument, not
    # a stopping condition discovered along the way.
    for number in range(1, arguments.pairs + 1):
        print(f"  paire {number}/{arguments.pairs}")
        pairs.append(one_pair(arguments.budget))
        if output:
            # Written at every pair: an interrupted measurement keeps what
            # it has already established, like a campaign's audit trail.
            output.write_text(json.dumps(pairs, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    _summary(pairs, arguments.budget)
    return pairs


def _summary(pairs, budget):
    if not pairs:
        return
    print(f"\n=== Bilan sur {len(pairs)} paire(s), budget {budget} ===\n")
    print(f"{'':12s} {'findings':>10s} {'modules':>9s} {'non scor.':>10s}")
    for arm in ("adaptive", "static"):
        average = {key: sum(p[arm][key] for p in pairs) / len(pairs)
                   for key in ("findings", "modules", "non_scorable")}
        print(f"  {arm:10s} {average['findings']:>10.2f} "
              f"{average['modules']:>9.2f} {average['non_scorable']:>10.2f}")

    gaps = [p["adaptive"]["findings"] - p["static"]["findings"]
              for p in pairs]
    wins = sum(1 for e in gaps if e > 0)
    losses = sum(1 for e in gaps if e < 0)
    print(f"\n  gap per pair: {gaps}")
    print(f"  the adaptive arm does better {wins}×, worse {losses}×, "
          f"level {len(gaps) - wins - losses}×")

    # The bias reminder, where the result is read: without it, a zero gap
    # would read as "adaptation brings nothing".
    print("\n  Reminder: the local judge misses one vulnerability in two, "
          "and adaptation")
    print("  feeds on the verdicts. A gain observed here is a LOWER BOUND;")
    print("  an absence of gain supports no conclusion at all.")


if __name__ == "__main__":
    main()
