"""
evaluation/measure_modes.py — MODE against MODE: does `--multiturn` find more
than a single-turn campaign, at equal cost to the target?

This is the comparison the recorded PyRIT condition asks for — "the sequenced
form demonstrated at the CAMPAIGN level under a protocol declared
beforehand" — and it is the one question about multi-turn that is still both
sound and unanswered.

WHAT IT IS NOT
--------------
It is NOT "does adaptation help". That question has no isolated answer with
the tool as built, found on 2026-11-19 by inspecting what each arm sends:
`objective_for` hands PyRIT a goal derived from RECONNAISSANCE whenever the
plan filled an objective, and the payload's text is then never sent. So
adaptation and payload-use are COUPLED — vary one and you vary the other —
and a comparison of the two would measure "is a garak payload better than
llama3.2's improvised chit-chat". See `measure_adaptive.py`, which carries
that confound in its own docstring.

Mode against mode does not need them separated. An operator choosing
`--multiturn` buys the whole package, improvisation included, and that is
exactly what is compared here.

PROTOCOL, declared BEFORE running (2026-11-19)
-----------------------------------------------
  * TARGET: `demo`, ONE defence level, as every multi-turn measurement here.

  * NORMALISATION — EQUAL TARGET REQUESTS, and this is the decision that
    shapes the result. Not equal attempts, which would hand multi-turn ~4.5
    times the resources; not equal tokens, which cost cents on the paid plan
    and are nobody's constraint. The project's own recorded constraints on a
    real target are "the throughput the target allows", "the contractual
    testing window" and "the cost to the client if their target is billed by
    usage" — all three count REQUESTS TO THE TARGET.

    So: multi-turn gets `MULTI_ATTEMPTS` attempts of `TURNS` turns, and
    single-turn gets `MULTI_ATTEMPTS * TURNS` attempts of one message.

  * A DECLARED BIAS, FAVOURING MULTI-TURN. A single-turn campaign ALSO spends
    replay requests — `REPLAY_COUNT` re-sends for every disclosure — and
    replay is not a luxury: it is what lets a single-turn finding reach
    `high` severity at all. So the single-turn arm really spends MORE target
    requests than the budget above allows, and the gap is not fixed by
    shrinking it, because removing replay would change the mode rather than
    equalise it. The counts actually spent are MEASURED and reported, so a
    reader can see the size of the advantage rather than take it on trust.

  * UNIT AND PAIRING: `PAIRS` pairs. Each pair runs both modes BACK TO BACK
    against the same target, multi-turn first. A probabilistic target drifts,
    and running one mode to completion before the other would let drift
    masquerade as an effect — the same reason the string protocol plays a
    pair's two halves together.

  * OUTCOME: the number of findings a campaign reports. That is what an
    operator reads, and it already carries the judge's vote, the replay and
    the denominator states, because it is produced by the campaign itself and
    not reconstructed here.

  * TEST: one-sided paired sign test at the 0.05 threshold, hypothesis
    "multi-turn finds MORE". That is the hypothesis which would justify
    PyRIT, so it is the one declared. **If the result runs the other way, the
    reverse direction's p is reported too and flagged as NOT the declared
    test** — exactly as the adaptation series did on 2026-11-12, where the
    declared hypothesis gave p = 0.99 and the reverse gave 0.032.

  * NO STOPPING RULE. Stopping once a p crosses the threshold is optional
    stopping, and it inflates the error this protocol exists to avoid.

REPORTED BESIDE THE TEST, descriptive and NEVER tested
-------------------------------------------------------
  * target requests actually spent by each mode, which is the normalisation's
    own audit;
  * findings by CRITERION and by SEVERITY. A multi-turn campaign can never
    produce a `high` finding — `high` is reachable only through
    `("divulgation", "confirmed")` and replay re-sends one payload, which a
    conversation has none of. A tie in COUNT would therefore not be a tie in
    what the findings are worth;
  * coverage by family for each mode, which for multi-turn now reads as
    *aimed at* rather than *sent* — the overstatement corrected on
    2026-11-19, and this is the first measurement that exercises it.

WHAT IT CANNOT SAY
------------------
Nothing about a target other than `demo` at one level, nothing about
adaptation in isolation, and nothing about an engagement's economics beyond
the request count — a client billed per token would normalise differently,
and the module says so rather than pretending the choice is neutral.

Run it from the project root, in PyRIT's venv:
    .venv-pyrit/Scripts/python -m evaluation.measure_modes
"""

import argparse
import json
import math
import sys
from pathlib import Path
from console import write_in_utf8

# --- The declared protocol ---------------------------------------------------
TARGET = "demo"
# Multi-turn's budget. The single-turn arm gets MULTI_ATTEMPTS * TURNS
# attempts, so both spend the same number of requests to the target before
# replay.
MULTI_ATTEMPTS = 3
TURNS = 3
PAIRS = 20
THRESHOLD = 0.05


def sign_test(favourable, unfavourable):
    """P(X >= favourable) under the null, one-sided."""
    n = favourable + unfavourable
    if not n:
        return 1.0
    return sum(math.comb(n, k) for k in range(favourable, n + 1)) / 2 ** n


def counting(ask_target):
    """
    The target, wrapped so every request to it is counted.

    Explicit rather than read back from the audit trail: the normalisation is
    the heart of this protocol, so what it counts must be visible in the code
    that counts it, not inferred from a file written for another purpose.
    """
    calls = {"n": 0}

    def ask(message, history=None):
        calls["n"] += 1
        return (ask_target(message, history) if history is not None
                else ask_target(message))

    ask.conversation = getattr(ask_target, "conversation", False)
    return ask, calls


def one_campaign(ask_target, *, multiturn, attempts, turns, show):
    """
    One campaign, driven through `main.run_campaign` and nothing else.

    `MAX_ATTEMPTS` is a module constant rather than a parameter, so it is
    patched for the duration and restored — stated here rather than hidden,
    because a measurement that quietly rewrites the thing it measures is
    worth nothing.
    """
    import main
    import report

    counted, calls = counting(ask_target)
    original = main.MAX_ATTEMPTS
    main.MAX_ATTEMPTS = attempts
    try:
        result = main.run_campaign(
            ask_target=counted, target_name=TARGET,
            multiturn=multiturn or None,
            max_turns=turns if multiturn else None)
    finally:
        main.MAX_ATTEMPTS = original

    # THROUGH `build_report`, never off the raw result -- and that is not a
    # convenience. A campaign's finding carries `payload` and `verdict` as
    # sub-objects, and the criterion, the family and above all the SEVERITY
    # are DERIVED: severity by the rules in `report.py`, which is the one
    # place in this project that grades.
    #
    # Reading the REPORT's field names off the CAMPAIGN's result is exactly
    # what silenced this breakdown on the first run: three of the four came
    # back `None`, the by-criterion and by-severity lines printed nothing, and
    # the counts beside them were right -- so nothing looked broken. The
    # comparison lost was the one that matters most, since a tie in COUNT is
    # not a tie in WORTH.
    #
    # The same reason the example report is regenerated from `result.json`
    # rather than re-derived by hand: the JSON is the source of truth, every
    # rendering follows from it, and a second copy of the severity rule here
    # would drift from the one the operator's report shows.
    built = report.build_report(result, target=TARGET)
    findings = built["findings"]
    return {
        "findings": len(findings),
        "requests": calls["n"],
        "criteria": [finding["critere"] for finding in findings],
        "severities": [finding["severity"] for finding in findings],
        "families": sorted({finding["owasp_family"] or finding["technique"]
                            for finding in findings}),
        "aimed_from_objective": built["coverage"]["aimed_from_objective"],
    }


def measure(pairs=PAIRS, multi_attempts=MULTI_ATTEMPTS, turns=TURNS,
            output=None, show=print):
    from targets import choose_target
    from targets.conversation import require_conversation

    ask_target = choose_target(TARGET)
    require_conversation(ask_target, TARGET)

    single_attempts = multi_attempts * turns
    show(f"Protocol: {pairs} pair(s) against {TARGET}, one-sided paired sign "
         f"test at {THRESHOLD}.")
    show(f"Equal TARGET REQUESTS: multi-turn {multi_attempts} x {turns} "
         f"turns, single-turn {single_attempts} x 1 message.")
    show("The single-turn arm ALSO spends replay requests, which is what "
         "lets it reach")
    show("`high` severity at all — so the declared bias favours MULTI-TURN, "
         "and the")
    show("requests actually spent are measured below rather than assumed.\n")

    results = []
    for number in range(1, pairs + 1):
        # Multi-turn FIRST, then single-turn, back to back: the target drifts.
        multi = one_campaign(ask_target, multiturn="redteaming",
                             attempts=multi_attempts, turns=turns, show=show)
        single = one_campaign(ask_target, multiturn=None,
                              attempts=single_attempts, turns=None, show=show)
        results.append({"multi": multi, "single": single})
        show(f"  pair {number}/{pairs}  multi {multi['findings']} finding(s) "
             f"in {multi['requests']} request(s)   single "
             f"{single['findings']} in {single['requests']}")
        if output:
            Path(output).write_text(
                json.dumps({"complete": number == pairs, "pairs": results},
                           ensure_ascii=False, indent=2), encoding="utf-8")

    _summary(results, show)
    return results


def _summary(results, show=print):
    import collections

    if not results:
        return
    better = sum(1 for r in results
                 if r["multi"]["findings"] > r["single"]["findings"])
    worse = sum(1 for r in results
                if r["multi"]["findings"] < r["single"]["findings"])
    ties = len(results) - better - worse

    show(f"\n=== Summary over {len(results)} pair(s) ===\n")
    show(f"  multi-turn finds more : {better}")
    show(f"  single-turn finds more: {worse}")
    show(f"  tie                   : {ties}")

    p = sign_test(better, worse)
    show(f"\n  DECLARED test (multi-turn finds more): p = {p:.4f}")
    show(f"  {'SIGNIFICANT' if p < THRESHOLD else 'NOT significant'} at "
         f"{THRESHOLD}")
    if worse > better:
        # Reported, and flagged: the adaptation series of 2026-11-12 declared
        # one direction, saw the other, and said so. Quoting the reverse p as
        # if it had been the hypothesis is the p-hacking the protocol exists
        # to prevent.
        show(f"\n  /!\\ the result runs the OTHER way. For the record, and "
             f"NOT the declared test:")
        show(f"      single-turn finds more: p = {sign_test(worse, better):.4f}")

    for name, key in (("multi-turn ", "multi"), ("single-turn", "single")):
        total = sum(r[key]["findings"] for r in results)
        requests = sum(r[key]["requests"] for r in results)
        show(f"\n  {name}: {total} finding(s) over {requests} target "
             f"request(s)")
        for label, field in (("criteria ", "criteria"),
                             ("severities", "severities")):
            found = collections.Counter(
                value for r in results for value in r[key][field] if value)
            if found:
                show(f"    {label}: " + ", ".join(
                    f"{v} {c}" for v, c in found.most_common()))

    aimed = sum(r["multi"]["aimed_from_objective"] for r in results)
    if aimed:
        show(f"\n  {aimed} multi-turn attempt(s) pursued a RECONNAISSANCE "
             f"objective, so their")
        show("  OWASP family is what was aimed at and not what was sent.")


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="`--multiturn` against a single-turn campaign, at equal "
                    "cost to the target.")
    parser.add_argument("--pairs", type=int, default=PAIRS)
    parser.add_argument("--attempts", type=int, default=MULTI_ATTEMPTS,
                        help=f"multi-turn attempts (protocol: "
                             f"{MULTI_ATTEMPTS}); the single-turn arm gets "
                             f"this times the turns")
    parser.add_argument("--turns", type=int, default=TURNS)
    parser.add_argument("--output", default=None, metavar="FILE")
    arguments = parser.parse_args(arguments)

    departures = [
        text for text, changed in (
            (f"{arguments.pairs} pairs instead of {PAIRS}",
             arguments.pairs != PAIRS),
            (f"{arguments.attempts} attempts instead of {MULTI_ATTEMPTS}",
             arguments.attempts != MULTI_ATTEMPTS),
            (f"{arguments.turns} turns instead of {TURNS}",
             arguments.turns != TURNS),
        ) if changed]
    if departures:
        print("/!\\ Protocol CHANGED on the command line — exploratory "
              "result, not confirmatory:")
        for departure in departures:
            print(f"    {departure}")
        print()

    measure(arguments.pairs, arguments.attempts, arguments.turns,
            arguments.output)
    return 0


if __name__ == "__main__":
    write_in_utf8()
    raise SystemExit(main())
