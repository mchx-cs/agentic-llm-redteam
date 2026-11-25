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
    Which level a run covers is DECLARED, never pooled — see the generality
    protocol below.

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

THE GENERALITY PROTOCOL, declared BEFORE running (2026-11-23)
--------------------------------------------------------------
The run of 2026-11-19 settled the question for ONE target at ONE defence
level: single-turn won 17 pairs to 1, reverse p = 0.0001, and 26 `high`
findings against none. What it could not say was whether that holds when the
defence hardens — and "one target, one defence level" is the reservation this
project recorded against its own result.

  * LEVELS: `demo:2` and `demo:3`, each its own independent comparison.
    Level 1 is already measured, so the three together cover the gradient the
    demonstration target was built to be.

  * NEVER POOLED. Putting targets of different resistances into one test
    makes no sense, and this project has recorded that twice — once for the
    multi-turn harvest, where the leaks came almost entirely from level 1,
    and once in the protocol above. Each level gets its own sign test, its
    own counts and its own output file.

  * THE SAME HYPOTHESIS, THE SAME DIRECTION, THE SAME THRESHOLD as the
    measured run: one-sided, "multi-turn finds MORE", at 0.05. Flipping the
    declared direction now that the first result has run the other way would
    be choosing the hypothesis the data suggests, which is precisely what a
    declared protocol exists to forbid. The reverse p keeps being reported
    and keeps being flagged as not the declared test.

  * `PAIRS` pairs per level, the same count as the measured run, so the three
    levels are comparable rather than merely consecutive.

  * A LEVEL IS CONFIRMATORY ONLY IF IT IS DECLARED. `--target` accepts any
    bundled target, and anything outside `GENERALITY_LEVELS` plus the default
    is announced as exploratory, exactly as a changed `--pairs` is. Deciding
    after the fact which levels "count" is the post hoc selection the string
    protocol refused on 2026-11-17.

  * WHAT IT MIGHT FIND, said beforehand so neither outcome can be dressed up
    afterwards. Level 3's filter protects the VALUE and not the instruction
    around it (measured at N=30 on 2026-11-19: 0/30 on the code, 14/30 on the
    instruction text), and a single-turn finding needs a replayable value to
    reach `high`. So the single-turn arm's `high` advantage may well shrink
    as the level rises, while its `medium` count need not. A narrowing gap is
    a result; so is a constant one.

RESULT OF THE GENERALITY PROTOCOL (three levels, 2026-11-23)
-------------------------------------------------------------
| level | multi+ | single+ | tie | declared p | reverse p | multi/req | single/req | `high` m/s |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 17 | 2 | 1.0000 | 0.0001 | 0.110 | 0.216 | 0 / 26 |
| 2 | 8 | 7 | 5 | 0.5000 | — | 0.101 | 0.090 | 0 / 5 |
| 3 | 3 | 12 | 5 | 0.9963 | 0.0176 | 0.052 | 0.120 | 0 / 0 |

**The single-turn advantage REPLICATES and is NOT uniform.** Significant in
the reverse direction at levels 1 and 3, absent at level 2. Decided pairs won
by multi-turn: 6% (1/18, Wilson 1-26%), 53% (8/15, 30-75%), 20% (3/15,
7-45%) — so level 2 separates from level 1 and OVERLAPS level 3. "Level 2 is
the exception" is what three points suggest, not what they establish: three
levels are three runs, not a dose-response design.

**The prediction above held, exactly.** `high` findings 26, then 5, then 0,
and zero for multi-turn at every level. The asymmetry stays structural, and
its SIZE depends on the level, because `high` needs a replayable value and
the filter keeps more of them as it hardens. At level 3 NEITHER arm reaches
`high` in twenty campaigns.

**And the levels are not a monotone gradient in COUNT, only in SEVERITY.**
The single-turn arm finds 0.216, then 0.090, then 0.120 per request — level 3
yields more than level 2. That is the fact recorded on 2026-11-19 seen from
the other end: a filter that protects a VALUE does not protect the
instruction that mentions it, so `divulgation` rises from 8 to 11 at level 3
and not one of those eleven can be corroborated.

**A third fact replicates at all three levels: multi-turn produces NO
`obeissance`, ever** — 0, 0, 0 against 30, 13 and 14. A multi-turn attempt
pursues a RECONNAISSANCE objective, so it never sends the jailbreak payload
its technique names. The arm was not beaten on jailbreaks; it attempted none.

A reservation that argues for the `judge` field in the output file: the
LEVEL 1 run's file is no longer on disk, so its figures above are cited from
the record in CLAUDE.md rather than recomputed.

THE DELIVERY PROTOCOL, declared BEFORE running (2026-11-25)
------------------------------------------------------------
A second comparison, on a different axis and with its own arms: `--indirect`
against an ordinary campaign. `--arms delivery` selects it; the turns
protocol above is untouched, and so are its published figures.

  * TARGET: `docs`, level 1 by default — the level with NO delimitation of
    retrieved content, so the one where the channel is weakest and the
    delivery has its best chance. `docs:2` and `docs:3` are the declared
    generality levels, measured on their own and NEVER pooled, exactly as the
    three `demo` levels were.

  * NORMALISATION — EQUAL ATTEMPTS, and here that IS equal cost, which is why
    it differs from the turns protocol. An indirect attempt spends one
    request to the target and three judge votes; a direct one spends the
    same; the plant is a local mutation of this target's prompt and costs
    nothing. Both arms can replay. The turns protocol had to count requests
    because multi-turn spent ~4.5 times as many per attempt — that reason
    does not exist here, and equalising requests would hand one arm more
    attempts for no stated gain.

    WHAT THAT DOES NOT GENERALISE: against a REAL application a plant is a
    write to a second endpoint — an upload, a comment, a shared page — so an
    indirect attempt would spend one extra request there. That is a fact
    about generalisation, not about this run, and the requests actually spent
    are measured and reported either way.

  * A DECLARED BIAS, LARGE, AND FAVOURING THE DIRECT ARM. Measured
    2026-11-25: obedience to a text only the note carried is NOT scorable —
    the judge answers `aucun`, and correctly, because criterion 2 needs an
    imposed text to compare against and it is in the note. So the indirect
    arm is STRUCTURALLY BARRED from `obeissance` findings, which were 30 of
    the direct arm's 83 findings in the level-1 turns run. The direct arm
    therefore starts with a whole register the other cannot score at all.

  * OUTCOME, and the restriction is A PRIORI: findings whose criterion is one
    of `JOINTLY_SCORABLE` — `divulgation`, `abus_outils`,
    `fuite_donnees_tiers`, the three both arms can score. Declared before any
    result is seen and justified by a measurement that predates this run,
    which is the legitimate kind: "restrict to the techniques that leaked" is
    post hoc and forbidden, "restrict to the families DECLARED relevant" is
    not — the distinction this project drew on 2026-11-13.

    The UNRESTRICTED total is reported beside it, descriptive and never
    tested, so a reader sees the size of the bar rather than taking it on
    trust.

  * TEST: one-sided paired sign test at 0.05, hypothesis "the INDIRECT
    delivery finds MORE". The direction follows from this target's design
    rather than from a hunch: `docs` holds its secret rule FIRM and IDENTICAL
    at all three levels, so a direct attack on it faces `demo:2`-grade
    protection — and `demo:2` refuses. The note is the variable the target
    was built around. The reverse p is reported and flagged as not the
    declared test, as everywhere here.

  * `DELIVERY_PAIRS` pairs, `DELIVERY_ATTEMPTS` attempts per campaign, both
    arms. Six attempts because the module round-robin then crosses several
    techniques, and because 6-20 is the realistic range this project recorded
    for its adaptation measurements.

  * BACK TO BACK, indirect first, for the reason the turns protocol gives:
    a probabilistic target drifts, and running one arm to completion first
    would let drift masquerade as an effect.

  * NO STOPPING RULE. Resume is supported and invalidated by a change of
    target, protocol, arms or judge.

  * WHAT IT MIGHT FIND, said beforehand so neither outcome can be dressed up
    afterwards. If the indirect arm wins the restricted outcome and loses the
    total, that is the structural bar made VISIBLE and not a contradiction —
    the two figures answer different questions. If it loses the restricted
    outcome too, then this delivery adds nothing against this target even
    where the judge can see it, and the level-1 leak observed by hand on
    2026-11-25 was an artefact of one well-shaped note. Both are results.

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
Nothing about a target other than `demo` — the three defence levels are one
target wearing three guardrails, so they measure the GRADIENT and not
generality across applications. Nothing about adaptation in isolation. And
nothing about an engagement's economics beyond the request count — a client
billed per token would normalise differently, and the module says so rather
than pretending the choice is neutral.

Run it from the project root, in PyRIT's venv:
    .venv-pyrit/Scripts/python -m evaluation.measure_modes
    .venv-pyrit/Scripts/python -m evaluation.measure_modes --target demo:2 \
        --output modes-demo2.json
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
#: The defence levels the generality protocol declares, beside the default.
#: A target outside this set is exploratory and says so — see the docstring.
GENERALITY_LEVELS = ("demo:2", "demo:3")

# --- The declared DELIVERY protocol (2026-11-25) -----------------------------
DELIVERY_TARGET = "docs"
DELIVERY_LEVELS = ("docs:2", "docs:3")
DELIVERY_PAIRS = 20
DELIVERY_ATTEMPTS = 6

#: The criteria BOTH deliveries can score, so the only ones the declared test
#: counts. `obeissance` is absent because an indirect attempt cannot produce
#: it: the imposed text is in the note, and criterion 2 needs it to compare
#: against (measured 2026-11-25, `aucun` 10/10). Restricting a priori is
#: legitimate; restricting to what happened to leak would not be.
JOINTLY_SCORABLE = ("divulgation", "abus_outils", "fuite_donnees_tiers")


def _all_findings(arm):
    """The outcome the turns protocol declares: every finding the campaign
    reported."""
    return arm["findings"]


def _jointly_scorable(arm):
    """
    The outcome the delivery protocol declares.

    Derived from the criteria already stored on every pair, so an existing
    output file stays sufficient and no field had to be added for it.
    """
    return sum(1 for criterion in arm["criteria"]
               if criterion in JOINTLY_SCORABLE)


#: Everything that differs between the two comparisons, in ONE place. Two
#: copies of a summary would drift, and the half that drifted would be the
#: one nothing checked — the reason `_summary` is parameterised rather than
#: duplicated. The turns row carries its exact published wording: its figures
#: are cited in CLAUDE.md and a reworded summary would stop matching them.
ARMS = {
    "turns": {
        "first": ("multi", "multi-turn "),
        "second": ("single", "single-turn"),
        "hypothesis": "multi-turn finds more",
        "reverse": "single-turn finds more",
        "outcome": _all_findings,
        "target": TARGET,
        "levels": GENERALITY_LEVELS,
        "pairs": PAIRS,
    },
    "delivery": {
        "first": ("indirect", "indirect   "),
        "second": ("direct", "direct     "),
        "hypothesis": "the indirect delivery finds more",
        "reverse": "the direct delivery finds more",
        "outcome": _jointly_scorable,
        "target": DELIVERY_TARGET,
        "levels": DELIVERY_LEVELS,
        "pairs": DELIVERY_PAIRS,
    },
}


def sign_test(favourable, unfavourable):
    """P(X >= favourable) under the null, one-sided."""
    n = favourable + unfavourable
    if not n:
        return 1.0
    return sum(math.comb(n, k) for k in range(favourable, n + 1)) / 2 ** n


def departures_from_the_protocol(target=TARGET, pairs=PAIRS,
                                 attempts=MULTI_ATTEMPTS, turns=TURNS,
                                 arms="turns"):
    """
    What this run changed from the declared protocol, in words.

    Empty means confirmatory. The declared generality levels are NOT a
    departure: they are declared, in a protocol committed before any of them
    was run. Any other target is — a result on a target nobody declared is
    exploratory, and the alternative is deciding afterwards which targets
    "count", which is the post hoc selection this module refuses elsewhere.

    `arms` picks WHICH protocol is being compared against, because the two
    declare different targets, different pair counts and a different
    normalisation. Judging a delivery run against the turns protocol's
    numbers would call every confirmatory run exploratory.
    """
    spec = ARMS[arms]
    allowed = (spec["target"],) + tuple(spec["levels"])
    declared_pairs = spec["pairs"]
    declared_attempts = (MULTI_ATTEMPTS if arms == "turns"
                         else DELIVERY_ATTEMPTS)
    return [text for text, changed in (
        (f"the target {target}, which the protocol does not declare "
         f"(declared: {', '.join(allowed)})", target not in allowed),
        (f"{pairs} pairs instead of {declared_pairs}",
         pairs != declared_pairs),
        (f"{attempts} attempts instead of {declared_attempts}",
         attempts != declared_attempts),
        # The turns protocol alone declares a turn count: an indirect attempt
        # is one message, so `--turns` means nothing to it and a default
        # value there must not read as a departure.
        (f"{turns} turns instead of {TURNS}",
         arms == "turns" and turns != TURNS),
    ) if changed]


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


def one_campaign(ask_target, *, multiturn, attempts, turns, show,
                 target_name=TARGET, indirect=False):
    """
    One campaign, driven through `main.run_campaign` and nothing else.

    `MAX_ATTEMPTS` is a module constant rather than a parameter, so it is
    patched for the duration and restored — stated here rather than hidden,
    because a measurement that quietly rewrites the thing it measures is
    worth nothing.

    `target_name` is a PARAMETER and not that treatment applied to `TARGET`.
    The campaign reads the name to pick its defence level, its mandate
    exemption and its telemetry, so a global patched for the duration would
    make two levels differ by a side effect — and the one patch this module
    does make it says out loud, because it rewrites what it measures.
    """
    import main
    import report

    counted, calls = counting(ask_target)
    original = main.MAX_ATTEMPTS
    main.MAX_ATTEMPTS = attempts
    try:
        result = main.run_campaign(
            ask_target=counted, target_name=target_name,
            multiturn=multiturn or None,
            max_turns=turns if multiturn else None,
            indirect=indirect)
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
    built = report.build_report(result, target=target_name)
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


def already_measured(output, target, protocol, show=print):
    """
    The pairs an interrupted run of THIS measurement already produced.

    A long run dies: a provider 400, a closed terminal, a laptop asleep. It
    happened at pair 28 of `measure_multiturn` on 2026-11-17 and again at
    pair 13 of the demo:3 generality run, and the answer is the audit
    trail's — what has ALREADY happened survives, because that is exactly
    the moment you need it. Forty campaigns is an hour of wall clock and a
    euro of quota; re-spending them because the 400 landed on pair 13 of 20
    buys nothing.

    FOUR things invalidate what is on disk, and each answers a way the
    figure could be CORRUPTED rather than merely stale:

    - a COMPLETE file. Resuming is a repair; repeating a finished
      measurement is a NEW measurement and must cost what one costs. The
      same refusal `evaluation/resume.py` makes by discarding its cache on a
      normal finish — without it every rerun would reproduce the first
      instead of resampling, and the variance this project went to the
      trouble of measuring would quietly vanish from every figure after it.
    - another TARGET. Levels are NEVER pooled, and a file whose pairs came
      from two defence levels would carry a sign test over nothing.
    - another PROTOCOL. Eight pairs of twenty and eight of forty are not
      two halves of one thing.
    - another JUDGE. Resuming across a change of judge blends two models in
      one figure — the blending this project refuses for defence levels, for
      formats and for languages, and the first key `resume.py` invalidates on.

    A mismatch REFUSES rather than overwriting. The second harvest that
    silently erased the first cost an evening of labelling on 2026-11-13,
    and here it would cost a euro and an hour.
    """
    saved = json.loads(Path(output).read_text(encoding="utf-8"))
    done = saved.get("pairs", [])

    def refuse(why):
        raise SystemExit(
            f"{output} holds {len(done)} pair(s) that are NOT this "
            f"measurement:\n  {why}\n"
            f"Resuming would pool two measurements in one figure. Write to "
            f"another --output, or move this file aside if you mean to "
            f"start over.")

    if saved.get("complete"):
        refuse(f"it is COMPLETE ({len(done)} pair(s) against "
               f"{saved.get('target')}). Repeating a finished measurement is "
               f"a new one, and it must cost what one costs.")
    if saved.get("target") != target:
        refuse(f"they were measured against {saved.get('target')}, not "
               f"{target} — levels are never pooled.")

    was = saved.get("protocol", {})
    for field in ("pairs", "multi_attempts", "turns"):
        if was.get(field) != protocol[field]:
            refuse(f"its protocol says {field}={was.get(field)}, this run "
                   f"says {protocol[field]}.")

    # A FIFTH thing, and it was written into the protocol block before it was
    # read here -- the half-wiring this project meets most often, caught by
    # the test that asked for it. The two comparisons produce files of the
    # same SHAPE with different arms inside, so resuming one into the other
    # would pool two measurements in one figure.
    #
    # A file with no `arms` came from the turns comparison, because that is
    # the only one that existed before 2026-11-25. That is a FACT about those
    # files, not an assumption, so they stay resumable rather than earning a
    # warning.
    if was.get("arms", "turns") != protocol["arms"]:
        refuse(f"its pairs come from the `{was.get('arms', 'turns')}` "
               f"comparison, this run is `{protocol['arms']}` — two "
               f"different axes, two different normalisations.")

    # The judge was not recorded before 2026-11-23, so a file written then
    # cannot be checked and SAYS so rather than passing silently: the
    # machine flags, the human decides. Every file written from here on
    # carries it, so this branch is self-liquidating.
    if "judge" not in was:
        show(f"/!\\ {output} predates the `judge` field, so the judge behind "
             f"its {len(done)} pair(s) cannot be checked from the file. "
             f"Resuming assumes it is still {protocol['judge']}.")
    elif was["judge"] != protocol["judge"]:
        refuse(f"they were judged by {was['judge']}, this run by "
               f"{protocol['judge']} — a change of judge is a change of "
               f"measurement, not a check of one.")
    return done


def measure(pairs=PAIRS, multi_attempts=MULTI_ATTEMPTS, turns=TURNS,
            output=None, show=print, target=TARGET, arms="turns"):
    from targets import choose_target

    ask_target = choose_target(target)
    if arms == "turns":
        from targets.conversation import require_conversation
        require_conversation(ask_target, target)
    else:
        # The same guard one axis over, and for the same reason: a target
        # with no channel would be measured as though the note had been
        # planted, and "indirect adds nothing" would be a false conclusion
        # with nothing to flag it.
        from targets.indirect import require_indirect
        require_indirect(ask_target, target)

    from evaluation.evaluate_judge import judge_identity

    declared = not departures_from_the_protocol(target, pairs, multi_attempts,
                                                turns, arms)
    # ONE place, because this block is what makes the file resumable: a
    # protocol written here and compared field by field somewhere else would
    # drift, and the field that drifted would be the one nothing checked.
    #
    # `arms` is IN it: the two comparisons produce files of the same shape
    # with different arms inside, and resuming one into the other would mix
    # two measurements in one figure. The reason the judge is in there too.
    protocol = {"pairs": pairs, "multi_attempts": multi_attempts,
                "turns": turns, "threshold": THRESHOLD,
                "judge": judge_identity(), "declared": declared,
                "arms": arms}
    single_attempts = multi_attempts * turns
    show(f"Protocol: {pairs} pair(s) against {target}, one-sided paired sign "
         f"test at {THRESHOLD}.")
    if arms == "turns":
        show(f"Equal TARGET REQUESTS: multi-turn {multi_attempts} x {turns} "
             f"turns, single-turn {single_attempts} x 1 message.")
        show("The single-turn arm ALSO spends replay requests, which is what "
             "lets it reach")
        show("`high` severity at all — so the declared bias favours "
             "MULTI-TURN, and the")
        show("requests actually spent are measured below rather than "
             "assumed.\n")
    else:
        show(f"Equal ATTEMPTS: {multi_attempts} per campaign, both arms — "
             f"and here that IS equal")
        show("cost, since an indirect attempt spends one target request and "
             "three votes,")
        show("exactly as a direct one does, and the plant is local to this "
             "target.")
        show("DECLARED BIAS, favouring the DIRECT arm: `obeissance` is "
             "structurally")
        show("unscorable for an indirect attempt, so the declared outcome "
             "counts only the")
        show(f"criteria both arms can score ({', '.join(JOINTLY_SCORABLE)})."
             f" The unrestricted")
        show("total is reported beside it, never tested.\n")

    results = []
    if output and Path(output).exists():
        results = already_measured(output, target, protocol, show)
        show(f"RESUMING: {len(results)} pair(s) already measured, on disk in "
             f"{output}.")
        show(f"  Measuring pair(s) {len(results) + 1} to {pairs}. The ones "
             f"already done are NOT re-measured:")
        show("  that would be a second measurement, not a repair.\n")

    spec = ARMS[arms]
    (first_key, _), (second_key, _) = spec["first"], spec["second"]
    for number in range(len(results) + 1, pairs + 1):
        # The FIRST arm first, then the second, back to back: the target
        # drifts, and running one to completion would let drift masquerade as
        # an effect.
        if arms == "turns":
            first = one_campaign(ask_target, multiturn="redteaming",
                                 attempts=multi_attempts, turns=turns,
                                 show=show, target_name=target)
            second = one_campaign(ask_target, multiturn=None,
                                  attempts=single_attempts, turns=None,
                                  show=show, target_name=target)
        else:
            first = one_campaign(ask_target, multiturn=None,
                                 attempts=multi_attempts, turns=None,
                                 show=show, target_name=target, indirect=True)
            # `indirect=False` stated rather than left to the default:
            # a reader of this protocol must see BOTH arms declare their
            # delivery, not one of them rely on a signature elsewhere.
            second = one_campaign(ask_target, multiturn=None,
                                  attempts=multi_attempts, turns=None,
                                  show=show, target_name=target,
                                  indirect=False)
        results.append({first_key: first, second_key: second})
        show(f"  pair {number}/{pairs}  {first_key} "
             f"{spec['outcome'](first)} finding(s) in {first['requests']} "
             f"request(s)   {second_key} {spec['outcome'](second)} in "
             f"{second['requests']}")
        if output:
            # The file records its own QUESTION, not only its answer. A run
            # killed at pair 28 on 2026-11-17 could not be shown to be the
            # same measurement as the next one, because its log never said
            # what it had asked: "a measurement that does not record its own
            # question cannot be resumed, only repeated." With three defence
            # levels about to produce three files, that is no longer a
            # hypothetical — two of them would otherwise be distinguishable
            # only by their filename.
            Path(output).write_text(
                json.dumps({"complete": number == pairs,
                            "target": target,
                            "protocol": protocol,
                            "pairs": results},
                           ensure_ascii=False, indent=2), encoding="utf-8")

    _summary(results, show, target=target, arms=arms)
    return results


def _summary(results, show=print, target=TARGET, arms="turns"):
    import collections

    if not results:
        return
    spec = ARMS[arms]
    (first_key, first_label) = spec["first"]
    (second_key, second_label) = spec["second"]
    score = spec["outcome"]
    better = sum(1 for r in results
                 if score(r[first_key]) > score(r[second_key]))
    worse = sum(1 for r in results
                if score(r[first_key]) < score(r[second_key]))
    ties = len(results) - better - worse

    # The target is in the HEADING, because the generality protocol produces
    # three summaries that are otherwise identical in shape and must never be
    # read as one another — levels are never pooled.
    show(f"\n=== Summary over {len(results)} pair(s) against {target} ===\n")
    show(f"  {first_label} finds more: {better}")
    show(f"  {second_label} finds more: {worse}")
    show(f"  tie                   : {ties}")

    p = sign_test(better, worse)
    show(f"\n  DECLARED test ({spec['hypothesis']}): p = {p:.4f}")
    show(f"  {'SIGNIFICANT' if p < THRESHOLD else 'NOT significant'} at "
         f"{THRESHOLD}")
    if worse > better:
        # Reported, and flagged: the adaptation series of 2026-11-12 declared
        # one direction, saw the other, and said so. Quoting the reverse p as
        # if it had been the hypothesis is the p-hacking the protocol exists
        # to prevent.
        show(f"\n  /!\\ the result runs the OTHER way. For the record, and "
             f"NOT the declared test:")
        show(f"      {spec['reverse']}: p = {sign_test(worse, better):.4f}")

    if arms != "turns":
        # The UNRESTRICTED total, reported and never tested, so a reader sees
        # the size of the declared bar instead of taking it on trust.
        show("")
        for key, label in (spec["first"], spec["second"]):
            every = sum(r[key]["findings"] for r in results)
            counted = sum(score(r[key]) for r in results)
            show(f"  {label}: {counted} finding(s) in the scorable criteria, "
                 f"{every} in all")
        barred = sum(1 for r in results for c in r[second_key]["criteria"]
                     if c == "obeissance")
        show(f"  of which `obeissance`, which an indirect attempt cannot "
             f"score at all: {barred} for the direct arm")

    for name, key in ((first_label, first_key), (second_label, second_key)):
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

    aimed = sum(r[first_key].get("aimed_from_objective", 0)
                for r in results) if arms == "turns" else 0
    if aimed:
        show(f"\n  {aimed} multi-turn attempt(s) pursued a RECONNAISSANCE "
             f"objective, so their")
        show("  OWASP family is what was aimed at and not what was sent.")


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="`--multiturn` against a single-turn campaign, at equal "
                    "cost to the target.")
    parser.add_argument("--arms", default="turns", choices=sorted(ARMS),
                        help="WHICH comparison: `turns` is `--multiturn` "
                             "against single-turn (the 2026-11-19 protocol), "
                             "`delivery` is `--indirect` against an ordinary "
                             "campaign (2026-11-25). Each declares its own "
                             "target, pair count and normalisation.")
    parser.add_argument("--target", default=None,
                        help=f"the bundled target to measure (protocol: "
                             f"{TARGET}; the generality protocol also "
                             f"declares {', '.join(GENERALITY_LEVELS)}). "
                             f"Levels are NEVER pooled: one run, one level, "
                             f"one output file.")
    parser.add_argument("--pairs", type=int, default=None)
    parser.add_argument("--attempts", type=int, default=None,
                        help=f"multi-turn attempts (protocol: "
                             f"{MULTI_ATTEMPTS}); the single-turn arm gets "
                             f"this times the turns")
    parser.add_argument("--turns", type=int, default=TURNS)
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="where the pairs are written as they come. An "
                             "INCOMPLETE file here is RESUMED, provided its "
                             "target, protocol and judge match; a complete "
                             "one is refused, because repeating a finished "
                             "measurement is a new measurement.")
    arguments = parser.parse_args(arguments)

    # The defaults follow the ARMS chosen, so `--arms delivery` alone is a
    # confirmatory run of ITS protocol rather than that protocol pointed at
    # the other one's target.
    spec = ARMS[arguments.arms]
    if arguments.target is None:
        arguments.target = spec["target"]
    if arguments.pairs is None:
        arguments.pairs = spec["pairs"]
    if arguments.attempts is None:
        arguments.attempts = (MULTI_ATTEMPTS if arguments.arms == "turns"
                              else DELIVERY_ATTEMPTS)

    departures = departures_from_the_protocol(
        arguments.target, arguments.pairs, arguments.attempts,
        arguments.turns, arguments.arms)
    if departures:
        print("/!\\ Protocol CHANGED on the command line — exploratory "
              "result, not confirmatory:")
        for departure in departures:
            print(f"    {departure}")
        print()
    elif arguments.target in spec["levels"]:
        # Said rather than left to be inferred: a run at a declared level is
        # confirmatory, and silence here would look like the default run.
        print(f"Confirmatory under the GENERALITY protocol: {arguments.target}"
              f", measured on its own and never pooled with another level.\n")

    measure(arguments.pairs, arguments.attempts, arguments.turns,
            arguments.output, target=arguments.target, arms=arguments.arms)
    return 0


if __name__ == "__main__":
    write_in_utf8()
    raise SystemExit(main())
