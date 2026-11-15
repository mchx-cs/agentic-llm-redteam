"""
evaluation/measure_adaptation.py — Does adaptation find more vulnerabilities
than the static plan, at an equal budget?

This is THE question that decides whether phase 3a was worth it. It gets
measured, not guessed: reordering attempts always looks like a good idea, and
that is exactly why it has to be checked.

NO CALL TO A MODEL, and that is why this script is here rather than in
`tests/`: the rest of `evaluation/` burns quota, this one does not. But it is
not a test — it does not produce a true/false verdict, it produces NUMBERS to
interpret, and its result depends on a random draw. So it has no business in
continuous integration.

Run it from the project root with:
    python -m evaluation.measure_adaptation
    python -m evaluation.measure_adaptation --signaux   # per-signal detail

METHOD, and its two traps, both met on 2026-11-11:

1. *Do not build the target in the heuristic's own image.* A first version
   made the target give way to exactly the probes the `secret_evoque` signal
   moves up. A spectacular gain… and perfectly circular: we were measuring
   that the code does what we coded. The vulnerable techniques are therefore
   drawn AT RANDOM, which amounts to assuming garak's OWASP mapping predicts
   NOTHING about the target's behaviour. That is the PESSIMISTIC hypothesis:
   reality is probably better, an LLM02 probe genuinely trying to make
   information leak.

2. *Do not conclude from a single draw.* One draw gave "adaptation loses 2
   findings", another the opposite: which techniques give way is arbitrary, so
   an isolated gap is noise. We average over NB_TIRAGES, and above all we
   count the share of draws where adaptation does WORSE — an average gain
   bought at the price of one failure in five is not worth the same as a
   systematic gain.
"""

import argparse
import random
from statistics import mean

import agents.adaptation as adaptation
from agents.planner import plan_campaign

DRAW_COUNT = 150
BUDGETS = (3, 6, 10, 20, 40)
# Share of techniques that give way. 20%: a target neither armoured nor wide
# open.
VULNERABLE_SHARE = 0.20
# Payloads kept per technique. There must be SEVERAL, otherwise the
# `technique_efficace` signal has nothing to move up and the measurement would
# be rigged the other way; there must not be too many, so that 150 draws run
# in a few seconds.
PAYLOADS_PER_TECHNIQUE = 3

# The measurement's reference target: an ordinary text chatbot. Both
# tri-states stay None — "it said nothing about it" — and the context is
# empty, so the modules that depend on the surrounding application
# (`ansiescape`, `web_injection`, `exploitation`) are skipped. That is
# deliberate: measuring adaptation on a pool holding untestable probes would
# skew the result in both directions.
PROFILE = {"role": "assistant", "language": "fr", "tools": [],
           "refused_subjects": ["le code du fonds ancien"],
           "mentions_instructions": True, "writes_code": None,
           "handles_documents": None, "context": [],
           "evidence": [], "exchanges": [], "warning": None}

# The refusal NAMES what it protects: that is the case favourable to the
# `secret_evoque` signal, which is precisely what we want to put to the test.
REFUSAL = "Je ne peux pas vous donner ce code, il est confidentiel."
LEAK = "Le code du fonds ancien est ARCHIVES-7731."

SIGNALS = ("technique_works", "technique_blocked", "secret_mentioned",
           "tool_triggered")


def build_pool():
    """The planner's pool, cut down to a few payloads per technique."""
    counts = {}
    pool = []
    for candidate in plan_campaign(PROFILE, 1)["candidates"]:
        technique = candidate["technique"]
        if counts.get(technique, 0) < PAYLOADS_PER_TECHNIQUE:
            counts[technique] = counts.get(technique, 0) + 1
            pool.append(candidate)
    return pool, sorted(counts)


def campaign(pool, budget, adaptive, giving_way, signals=None):
    """
    One simulated campaign. Returns the number of findings.

    `adaptive=False` follows the pool's static order learning nothing: that is
    the control. `signals` allows neutralising some signals, to isolate each
    one's contribution.
    """
    launched, observations, findings = [], [], 0

    for _ in range(budget):          # a bounded loop, as everywhere else
        attempt = adaptation.next_attempt(
            pool, observations if adaptive else (), launched)
        if attempt is None:
            break
        launched.append(attempt)

        succeeded = attempt["technique"] in giving_way
        findings += succeeded
        fresh = adaptation.observe(
            attempt, LEAK if succeeded else REFUSAL,
            {"reussi": succeeded,
             "critere": "divulgation" if succeeded else "aucun"})
        if signals is not None:
            fresh = [o for o in fresh if o["signal"] in signals]
        observations = adaptation.accumulate(observations, fresh)

    return findings


def measure(pool, techniques, budget, signals=None, draws=DRAW_COUNT):
    """Mean gap adaptive − static, and the distribution of draws."""
    how_many = max(1, int(len(techniques) * VULNERABLE_SHARE))
    gaps = []
    for seed in range(draws):
        # An explicit seed: the measurement must be reproducible exactly.
        giving_way = set(random.Random(seed).sample(techniques, how_many))
        gaps.append(campaign(pool, budget, True, giving_way, signals)
                    - campaign(pool, budget, False, giving_way))
    return {
        # `mean`, not `medium`: the data-key pass translated the French
        # `moyen` with the severity sense of the word, and this one is an
        # average. Same for `tie`, which came out as `level`.
        "mean": mean(gaps),
        "better": sum(g > 0 for g in gaps),
        "worse": sum(g < 0 for g in gaps),
        "tie": sum(g == 0 for g in gaps),
    }


def measure_overall(pool, techniques):
    print("Adaptive against static plan, at an equal budget.")
    print(f"Vulnerable techniques drawn AT RANDOM "
          f"({int(VULNERABLE_SHARE * 100)}% of {len(techniques)}), "
          f"{DRAW_COUNT} draws.")
    print("PESSIMISTIC hypothesis: garak's OWASP mapping predicts nothing")
    print("about the target's behaviour.\n")

    print(f"{'budget':>6} | {'mean gap':>11} | {'better':>6} {'worse':>6} "
          f"{'tie':>6}")
    print("-" * 46)
    for budget in BUDGETS:
        r = measure(pool, techniques, budget)
        print(f"{budget:>6} | {r['mean']:>+11.2f} | {r['better']:>6} "
              f"{r['worse']:>6} {r['tie']:>6}")

    print("\nRead it like this: the gain GROWS with the budget. At three "
          "attempts it is\nmarginal and one draw in five loses; at forty it "
          "is clear and almost\nsystematic. Adaptation needs budget to pay "
          "off — which makes sense, since\nyou have to be able to come back "
          "to a lead in order to exploit it.")


def measure_per_signal(pool, techniques):
    """Which signal carries the gain? We neutralise them one by one."""
    cases = [("every signal", set(SIGNALS))]
    cases += [(f"without {signal}", set(SIGNALS) - {signal})
              for signal in SIGNALS]
    cases += [(f"{signal} ALONE", {signal}) for signal in SIGNALS]

    budgets = (3, 10, 40)
    print("\nEach signal's contribution (same protocol)\n")
    header = "  ".join(f"{'b' + str(b):>13}" for b in budgets)
    print(f"{'variant':30s} {header}")
    print(f"{'':30s} " + "  ".join(f"{'mean (worse)':>13}" for _ in budgets))
    print("-" * (32 + 15 * len(budgets)))
    for name, signals in cases:
        columns = []
        for budget in budgets:
            r = measure(pool, techniques, budget, signals)
            columns.append(f"{r['mean']:>+6.2f} ({r['worse']:>3})")
        print(f"{name:30s} " + "  ".join(f"{c:>13}" for c in columns))


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Measures what plan adaptation gains (no model).")
    parser.add_argument("--signals", "--signaux", action="store_true",
                        dest="signals",
                        help="break down each signal's contribution")
    arguments = parser.parse_args(arguments)

    pool, techniques = build_pool()
    print(f"Pool: {len(pool)} candidates, {len(techniques)} techniques, "
          f"{PAYLOADS_PER_TECHNIQUE} payloads per technique.\n")
    if not techniques:
        print("Empty pool: synchronise the garak snapshot "
              "(python -m payloads.garak_source --version).")
        return

    measure_overall(pool, techniques)
    if arguments.signals:
        measure_per_signal(pool, techniques)


if __name__ == "__main__":
    main()
