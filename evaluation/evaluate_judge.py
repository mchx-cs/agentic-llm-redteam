"""
evaluation/evaluate_judge.py — Measures the judge's reliability (Phase 2).

The principle: we give the judge exchanges whose right answer we ALREADY know
(labelled by hand in labelled_exchanges.json), then count its mistakes.
Without that, there is no way to know whether a "vulnerability found" by a
campaign really is one.

The two errors do not cost the same:
- False positive (FP): the judge cries vulnerability where there is none. The
  final report would be polluted with false alarms.
- False negative (FN): the judge misses a real one. Worse for a security tool:
  the campaign wrongly concludes "no vulnerability".

Two sets, so as not to fool ourselves (overfitting):
- "dev"  : we tune the judge by looking at these results. In time they stop
           measuring the judge and start measuring our skill at fixing these
           particular cases.
- "test" : a FROZEN set. We consult it only at key moments, and we NEVER tune
           the judge from it. Every consultation is logged in
           test_set_log.jsonl: the discipline becomes verifiable.

Run it from the project root with:
    python -m evaluation.evaluate_judge            # the development set
    python -m evaluation.evaluate_judge --test     # the frozen test set
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from agents.judge import judge, judge_conversation
from config import JUDGE_PROFILE, PROFILES
from evaluation.resume import Cache
from console import write_in_utf8

EXCHANGES_FILE = Path(__file__).parent / "labelled_exchanges.json"
TEST_LOG = Path(__file__).parent / "test_set_log.jsonl"

# The judge the published 89 / 100 / 96 were measured on. Any other model is
# a different measurement, not a check of this one — and the project has
# changed judge model before (llama3.2 -> gpt-oss-120b lifted recall from
# 50% to 100%), so this will happen again.
MEASURED_ON = "groq/openai/gpt-oss-120b"


def judge_identity():
    """
    Names the judge being measured, as `profile/model`.

    ONE function, because this string is a KEY: it stamps the frozen-set
    log, it decides whether the published figures are comparable, and it
    keys the resume cache. Reassembled by hand in each of those places --
    as it was until 2026-11-16, four times over, plus a fifth in the tests
    -- the three could drift apart, and the one that must not is the cache:
    a key built differently from the one the cache was written with serves a
    verdict from another judge. The same argument as `question_asked`, which
    is built by the functions that build the real question rather than
    reconstructed.
    """
    return f"{JUDGE_PROFILE}/{PROFILES[JUDGE_PROFILE]['model']}"


def load_exchanges(dataset):
    """Loads one set's exchanges ("dev" or "test"), after checking."""
    from migration import modernise

    with open(EXCHANGES_FILE, encoding="utf-8") as f:
        exchanges = modernise(json.load(f))["exchanges"]

    # A guard: one scenario (a group) must NEVER be split between the two
    # sets. Otherwise the test set would hold a mere rewording of a dev case,
    # already "seen" during tuning: it would measure nothing at all.
    dataset_of_group = {}
    for exchange in exchanges:
        group = exchange["group"]
        dataset_of_group.setdefault(group, exchange["dataset"])
        if dataset_of_group[group] != exchange["dataset"]:
            raise ValueError(
                f"Group {group} is split between 'dev' and 'test' "
                f"({exchange['id']}): a leak between the two sets."
            )

    in_dataset = [e for e in exchanges if e["dataset"] == dataset]

    return in_dataset


# READ from `label`, never restated. One turn means the SINGLE-TURN
# instruction, which is the frozen artefact: an entry stored as `turns` but
# holding one exchange must be judged by the same bytes as the 90 exchanges
# the published figures were measured on.
#
# It moved there on 2026-11-24 so that `integrate()` — a pure data step —
# stops importing this module, and with it the judge and a provider's SDK.
from evaluation.label import is_conversation  # noqa: F401  (re-exported)


def question_asked(exchange):
    """
    The exact text the judge will be sent, for the resume cache's digest.

    Built by the SAME functions that build it for real, never reconstructed:
    a digest over a different string would silently let a stale verdict
    through, which is the one thing the cache must not do.
    """
    from agents.judge import build_conversation_question, build_question

    if is_conversation(exchange):
        return build_conversation_question(exchange["turns"])
    if exchange.get("turns"):
        return build_question(exchange["turns"][0]["content"],
                              exchange["turns"][1]["content"])
    return build_question(exchange["payload"], exchange["reply"])


def ask_the_judge(exchange, language):
    """
    One verdict, by whichever instruction the entry's format calls for.

    The two paths are DISTINCT functions in `agents.judge`, deliberately, so
    the caller has to declare which format it is judging. This is the caller,
    and it declares it from the data.
    """
    if is_conversation(exchange):
        # No `language` here: only the French instruction has been measured on
        # conversations, and there is nothing yet to compare an English one
        # against. Passing it silently would suggest a choice had been made.
        return judge_conversation(exchange["turns"])
    if exchange.get("turns"):
        # Stored as turns, but a single exchange: flatten to the two strings
        # the frozen instruction expects, rather than sending a one-turn
        # "conversation" through the multi-turn addendum.
        attacker, target = exchange["turns"][0], exchange["turns"][1]
        return judge(attacker["content"], target["content"], language)
    return judge(exchange["payload"], exchange["reply"], language)


def ratio(numerator, denominator):
    """Avoids a division by zero when a category is empty."""
    return numerator / denominator if denominator else 0.0


def as_percent(value, width=0):
    """A metric as a percentage, or `n/a` when it is undefined.

    One place, because the alternative is four print sites each deciding for
    themselves -- and one of them deciding wrongly is how `precision=0%`
    reached a published-looking line over a population with no positive
    verdict in it.
    """
    text = "n/a" if value is None else f"{value:.0%}"
    return f"{text:>{width}}" if width else text


def log_test_consultation(counts, metrics, language='fr'):
    """Appends a line to the log of frozen-set consultations."""
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        # Without the judge being measured, the log's lines would not be
        # comparable.
        "juge": judge_identity(),
        # The instruction's LANGUAGE, since 2026-11-14: two consultations
        # with two different instructions would otherwise be
        # indistinguishable in the log, and the frozen set would lose its
        # value as a reference.
        "instruction_language": language,
        **counts,
        **{name: round(value, 3) for name, value in metrics.items()},
    }
    with open(TEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _per_language(exchanges, results_by_id):
    """
    The same figures, split by language pair.

    WHY. The corpus mixes languages, and it did so silently until 2026-11-15.
    The judge's instruction is French, its seven examples are French, and an
    English attacker turn against a French reply is a population the corpus
    had never declared. An aggregate figure over two populations is the
    blending this project refuses elsewhere — it would not pool defence levels
    in the multi-turn measurement for the same reason.

    What this breakdown can and cannot give is asymmetric, and it says so: a
    population with no positive in it yields a false-positive rate and NO
    recall. Printing "recall: n/a" there is the honest answer; printing 0%
    would read as a judge that misses everything.
    """
    groups = {}
    for exchange in exchanges:
        pair = exchange.get("languages") or "unrecorded"
        groups.setdefault(pair, []).append(exchange)

    if len(groups) < 2:
        return

    print("\n--- Per language pair (attacker -> target) ---")
    print("A pair with no real vulnerability in it gives a false-positive "
          "rate and no recall; that is stated, not printed as 0%.")
    for pair in sorted(groups, key=lambda p: -len(groups[p])):
        subset = groups[pair]
        tp = sum(1 for e in subset
                 if results_by_id[e["id"]]["reussi"] and e["expected"])
        fp = sum(1 for e in subset
                 if results_by_id[e["id"]]["reussi"] and not e["expected"])
        tn = sum(1 for e in subset
                 if results_by_id[e["id"]]["reussi"] is False
                 and not e["expected"])
        positives = sum(1 for e in subset if e["expected"])
        recall = (f"{ratio(tp, positives):.0%}" if positives
                  else "n/a (no vulnerability in this pair)")
        print(f"  {pair:12s} {len(subset):>3} exchange(s), "
              f"{positives:>2} vulnerability(ies)  "
              f"TP={tp} FP={fp} TN={tn}  recall={recall}")


def scores(exchanges, results_by_id):
    """Precision, recall and accuracy over any subset. No printing."""
    tp = sum(1 for e in exchanges
             if results_by_id[e["id"]]["reussi"] and e["expected"])
    fp = sum(1 for e in exchanges
             if results_by_id[e["id"]]["reussi"] and not e["expected"])
    tn = sum(1 for e in exchanges
             if results_by_id[e["id"]]["reussi"] is False
             and not e["expected"])
    positives = sum(1 for e in exchanges if e["expected"])
    return {"n": len(exchanges), "tp": tp, "fp": fp, "tn": tn,
            "positives": positives,
            # None, never 0.0, when NO positive verdict was issued: the
            # ratio is undefined and a 0% reads as a judge that is always
            # wrong. The project's own rule, from the OWASP manual and
            # already applied to the ASR -- report undefined ratios as N/A.
            "precision": ratio(tp, tp + fp) if (tp + fp) else None,
            "rappel": ratio(tp, positives) if positives else None,
            "exactitude": ratio(tp + tn, len(exchanges))}


def criterion_precision(criterion, exchanges, results_by_id):
    """
    Precision for one criterion, attributed by the VERDICT and never by the
    label.

    A false positive belongs to the criterion the judge NAMED. A negative case
    has no true criterion at all -- its category says what kind of trap it is,
    not what the judge should have emitted -- so counting its false positive
    against the family it belongs to blames a criterion that never fired.

    It scans EVERY exchange of the run, not the criterion's own population: a
    verdict naming `divulgation` can land on a case of any family, and that is
    exactly the case this exists for.

    Returns None when the judge never named the criterion: an undefined ratio
    is reported as n/a and never as 0%, the project's rule from the OWASP
    manual.

    What it does NOT claim: "when it names c, there is a breach" is the
    question answered; "c was the right criterion" is a different one, and
    `criterion_agreement` is where that lives.
    """
    named = [e for e in exchanges
             if results_by_id[e["id"]]["reussi"] is True
             and (results_by_id[e["id"]].get("critere") or "") == criterion]
    if not named:
        return None, 0
    return sum(1 for e in named if e["expected"]) / len(named), len(named)


def criterion_agreement(exchanges, results_by_id):
    """
    Of the breaches BOTH sides saw, how many were given the same criterion.

    The exact sibling of `turn_agreement`, and for the same reason: a judge
    that finds every breach and names the wrong criterion every time scores
    100 / 100 / 100 on precision, recall and accuracy. That blind spot became
    visible only once a false positive was attributed by the verdict, which is
    when the verdict's criterion started being read at all.

    Scored ONLY where both sides committed: the case is a positive whose
    category maps to a criterion, and the judge found a breach and named one.
    Anything else is a disagreement about the BREACH, which recall counts.

    None rather than 0 when there is nothing to score -- a 0% would read as a
    judge that always picks the wrong criterion.
    """
    from evaluation.label import CRITERION_OF

    agreed = total = 0
    for exchange in exchanges:
        if not exchange["expected"]:
            continue
        expected = CRITERION_OF.get(exchange["category"])
        verdict = results_by_id[exchange["id"]]
        said = verdict.get("critere")
        if expected is None or verdict["reussi"] is not True or not said:
            continue
        total += 1
        agreed += (said == expected)
    return (agreed, total) if total else (None, 0)


def _per_criterion(exchanges, results_by_id):
    """
    The figures by CRITERION, each with the floor its positives support.

    Added after the audit of 2026-11-18, which looked at the corpus through
    its criteria for the first time: `divulgation` has 39 positives and the
    two newest criteria have 5 each. A single accuracy figure averages four
    levels of proof and reads as one, which is the lie by omission this
    project refuses everywhere else.

    The floor is `stats.wilson_interval(p, p)[0]` -- what a PERFECT recall
    still allows. "Caught 5 of 5" bounds the true rate at 57%, "39 of 39" at
    91%, and those are not the same claim.

    Printed in the corpus's own order of maturity rather than alphabetically,
    so a reader meets the well-covered criteria first and the thin ones last,
    where the floor is the point.
    """
    import stats
    from evaluation.label import CRITERION_OF

    unmapped = sorted({e["category"] for e in exchanges
                       if e["category"] not in CRITERION_OF})
    if unmapped:
        print(f"\n/!\\ categories with no criterion: {unmapped} — "
              f"add them to CRITERION_OF, or their rows mean nothing.")

    groups = {}
    for exchange in exchanges:
        criterion = CRITERION_OF.get(exchange["category"])
        if criterion is None:
            continue
        groups.setdefault(criterion, []).append(exchange)
    if len(groups) < 2:
        return

    print("\n--- Per criterion, with what each one's positives SUPPORT ---")
    print("A perfect recall on few positives bounds little: the floor says "
          "how little.")
    print("Recall and accuracy are over the criterion's own cases; PRECISION "
          "is over the")
    print("verdicts that NAMED it, because a false positive belongs to the "
          "criterion the")
    print("judge said and a negative case has no true criterion at all.")
    for criterion in sorted(groups, key=lambda c: -sum(
            1 for e in groups[c] if e["expected"])):
        subset = groups[criterion]
        s = scores(subset, results_by_id)
        if s["positives"]:
            floor = stats.wilson_interval(s["positives"],
                                          s["positives"])[0]
            bound = f"floor {floor:.0%} on {s['positives']} positive(s)"
            recall = f"{s['rappel']:.0%}"
        else:
            bound = "no positive: no recall measurable"
            recall = "n/a"
        # Precision is NOT s["precision"]: that one is attributed by the
        # label, which blames a criterion the judge never named. See
        # `criterion_precision`.
        precision, named = criterion_precision(criterion, exchanges,
                                               results_by_id)
        print(f"  {criterion:22s} {s['n']:3d} case(s)  "
              f"precision={as_percent(precision, 4)} on {named:2d} verdict(s)"
              f"  recall={recall:>4s}  "
              f"accuracy={as_percent(s['exactitude'])}   [{bound}]")

    # Controls carry no criterion and that is their job: they witness against
    # false positives, so they are counted apart rather than dropped.
    controls = [e for e in exchanges
                if CRITERION_OF.get(e["category"], "missing") is None]
    if controls:
        flagged = sum(1 for e in controls
                      if results_by_id[e["id"]]["reussi"])
        print(f"  {'controls':22s} {len(controls):3d} case(s), no criterion "
              f"to score — {flagged} wrongly flagged")


def _per_provenance(exchanges, results_by_id):
    """
    Author-labelled against model-labelled, never pooled.

    The project's rule is that labels are the AUTHOR's. 119 of them were
    decided by a model on 2026-11-16, at the author's explicit request, so
    the corpus now holds both -- and the two answer DIFFERENT questions:

      * on author-labelled entries the figure measures whether the judge is
        RIGHT;
      * on model-labelled ones it measures whether two models AGREE, which
        is a weaker claim and must never be quoted as the first.

    Pooling them averages a measurement with an agreement rate. Printing
    them apart is what lets one consultation of the frozen set -- which is
    logged, so it should happen ONCE -- answer both questions.
    """
    author = [e for e in exchanges if e.get("labelled_by") != "model"]
    model = [e for e in exchanges if e.get("labelled_by") == "model"]
    if not (author and model):
        return

    print("\n--- Per label provenance: never pooled ---")
    print("Author-labelled measures CORRECTNESS; model-labelled measures "
          "agreement between models.")
    for name, subset in (("author", author), ("model ", model)):
        s = scores(subset, results_by_id)
        recall = (f"{s['rappel']:.0%}" if s["rappel"] is not None
                  else "n/a (no vulnerability)")
        print(f"  {name}  {s['n']:>3} exchange(s), {s['positives']:>2} "
              f"vulnerability(ies)  "
              f"precision={as_percent(s['precision'])}  "
              f"recall={recall}  "
              f"accuracy={as_percent(s['exactitude'])}")


def _per_format(exchanges, results_by_id):
    """
    Single-turn and conversations, side by side and NEVER pooled.

    This is the point of the whole split. Until conversations entered the
    corpus, the headline figure was single-turn by construction, and that is
    what the published 89 / 100 / 96 describes. Pooling the two formats would
    silently turn it into a mixed figure, incomparable with every consultation
    logged since 2026-11-09 — the exact blending this project refuses when it
    declines to pool defence levels in one test.

    So the headline above is the POOLED one, printed because a reader asking
    for "set dev" expects to hear about set dev, and this block is what makes
    it readable: the single-turn line is the one to compare with history, the
    conversation line is a NEW measurement with no history to compare to.
    """
    single = [e for e in exchanges if not is_conversation(e)]
    conversations = [e for e in exchanges if is_conversation(e)]
    if not conversations or not single:
        return

    # The published figures were measured on ONE judge. Claiming the
    # single-turn line is comparable with them is only true on that judge —
    # on another model it is a different measurement, and saying otherwise
    # would invite exactly the comparison the separation exists to protect.
    current = judge_identity()
    same_judge = current == MEASURED_ON

    # Comparability has TWO conditions, and until 2026-11-17 only the first
    # was checked. The published figures were taken on one JUDGE and on one
    # POPULATION -- entries the author labelled. Once 119 model-labelled
    # entries joined the corpus, the single-turn line covered 109 entries on
    # `dev` where the figure came from 67, and still called itself
    # comparable. A line that LOOKS like the reference and is not is the
    # defect this whole split exists to prevent.
    borrowed = sum(1 for e in single if e.get("labelled_by") == "model")
    if not same_judge:
        single_note = (f"NOT comparable: those figures are {MEASURED_ON}, "
                       f"this is {current}")
    elif borrowed:
        single_note = (f"NOT comparable: {borrowed} of these {len(single)} "
                       f"entries are model-labelled; the published figures "
                       f"are author-labelled only. See the provenance split.")
    else:
        single_note = "comparable with 89 / 100 / 96"

    print("\n--- Per format: never pooled ---")
    print("Compare the single-turn line with the published figures; the "
          "conversation line is a new measurement with no history.")
    if not same_judge:
        print(f"!!! The judge is {current}, not {MEASURED_ON}. A change of "
              f"model is a change of\n    measurement: re-read the "
              f"single-turn line as a fresh baseline, not as a check.")
    for name, subset, note in (
            ("single-turn ", single, single_note),
            ("conversation", conversations, "NEW format, phase 3b")):
        if not subset:
            # A restricted run empties one arm. Printing `precision=0%` over
            # nothing -- and beside "comparable with 89 / 100 / 96" -- would
            # read as a judge that gets everything wrong, which is the same
            # mistake the report refuses when it prints "not calculable"
            # rather than a 0% success rate.
            print(f"  {name}   not measured in this run")
            continue
        s = scores(subset, results_by_id)
        recall = (f"{s['rappel']:.0%}" if s["rappel"] is not None
                  else "n/a (no vulnerability)")
        print(f"  {name}  {s['n']:>3} exchange(s), {s['positives']:>2} "
              f"vulnerability(ies)  precision={as_percent(s['precision'])}  "
              f"recall={recall}  accuracy={s['exactitude']:.0%}   [{note}]")


def turn_agreement(exchanges, results_by_id):
    """
    Of the breaches both the author and the judge saw, how many on the SAME
    turn.

    A SECOND measurement, kept apart from precision and recall on purpose. A
    judge can be right that the chatbot gave way and wrong about where, and
    the aggregate figure would never show it: `expected` is a boolean, so the
    turn has no way into it.

    Scored only where both sides committed — the author labelled a breach AND
    the judge found one AND both named a turn. Anything else is not a
    disagreement about the turn, it is a disagreement about the breach, and
    that is already counted above. Returns None when there is nothing to
    score, never 0: a 0% would read as a judge that always picks the wrong
    turn.
    """
    comparable = [
        (e["breach_turn"], results_by_id[e["id"]]["tour"])
        for e in exchanges
        if e.get("breach_turn") and e["expected"]
        and results_by_id[e["id"]]["reussi"]
        and results_by_id[e["id"]].get("tour")
    ]
    if not comparable:
        return None
    agreed = sum(1 for expected, obtained in comparable
                 if expected == obtained)
    return {"agreed": agreed, "comparable": len(comparable),
            "rate": ratio(agreed, len(comparable))}


def _print_turn_agreement(exchanges, results_by_id):
    agreement = turn_agreement(exchanges, results_by_id)
    if agreement is None:
        return
    print(f"\nTurn agreement: {agreement['agreed']}/"
          f"{agreement['comparable']} ({agreement['rate']:.0%}) — of the "
          f"breaches both sides saw, how many on the same turn.")


def _print_criterion_agreement(exchanges, results_by_id):
    """The sibling of the line above, and kept just as separate.

    Without it, a judge that finds every breach and names the WRONG criterion
    every time scores 100 / 100 / 100 on precision, recall and accuracy. That
    blind spot became visible only once false positives were attributed by the
    verdict, which is when the verdict's criterion started being read at all.
    """
    agreed, total = criterion_agreement(exchanges, results_by_id)
    if agreed is None:
        return
    print(f"Criterion agreement: {agreed}/{total} "
          f"({agreed / total:.0%}) - of the breaches both sides saw, how "
          f"many under the same criterion.")


def format_contribution(exchanges):
    """
    How many conversation breaches happened AFTER the first turn.

    The format's own contribution, and the reason `multitours-reussi` was
    removed rather than filled: this is criterion-independent, derived from
    `breach_turn` which is ground truth, and it covers every criterion where
    a category could only ever have covered one.

    Counted over the author's LABELS, never over the judge's verdicts: it
    describes what the corpus contains, not how well the judge reads it.

    Returns (late, positives) or (None, 0) when there is no conversation
    positive to count -- an undefined ratio is reported as n/a, never as 0%.
    """
    positives = [e for e in exchanges
                 if e["expected"] and e.get("turns")
                 and len(e["turns"]) > 2]
    if not positives:
        return None, 0
    return sum(1 for e in positives
               if (e.get("breach_turn") or 1) > 1), len(positives)


def _print_format_contribution(exchanges):
    late, positives = format_contribution(exchanges)
    if late is None:
        return
    print(f"Breach after the first turn: {late}/{positives} "
          f"({late / positives:.0%}) - of the conversation positives, how "
          f"many the FORMAT contributed to. A corpus fact, not a judge one.")


def evaluate(dataset="dev", language="fr", only=None):
    """
    Measures the judge, optionally on ONE format only.

    `only` ("conversations" or "single-turn") is a DIAGNOSTIC, added while
    tuning the multi-turn addendum: that work needs several passes over the
    45 conversations, and re-judging the 109 single-turn entries each time
    would pay ~3x for an answer about the other population.

    It is deliberately not a measurement. A restricted run announces itself
    and caches under its own scope, so it can never serve verdicts to a full
    run -- reuse between two different runs would be repeating a measurement,
    not resuming one, which is the line `resume.discard()` exists to hold.

    What it does NOT change is the comparability note: that note is about the
    single-turn LINE, which is the same population restricted or not, so
    suppressing it would be suppressing something true.
    """
    exchanges = load_exchanges(dataset)
    if only:
        wanted = only == "conversations"
        exchanges = [e for e in exchanges if is_conversation(e) is wanted]
    counts = {"VP": 0, "FP": 0, "VN": 0, "FN": 0, "a_revoir": 0}
    errors = []
    results_by_id = {}

    print(f"Judge: profile {JUDGE_PROFILE}, "
          f"model {PROFILES[JUDGE_PROFILE]['model']}\n")

    # Where the ground truth came from. The project's rule is that labels are
    # the AUTHOR's; a figure measured against a model's labels says "the judge
    # agrees with another model", which is a different claim and must not be
    # quoted as the first. Said at the TOP, before the figures, so it cannot
    # be read past.
    if only:
        print(f"!!! RESTRICTED to {only}: {len(exchanges)} of "
              f"{len(load_exchanges(dataset))} entries in `{dataset}`.")
        print(f"    This is a diagnostic, NOT the `{dataset}` "
              f"measurement, and it must not be quoted as one.")
        print()

    by_model = [e for e in exchanges if e.get("labelled_by") == "model"]
    if by_model:
        print(f"!!! {len(by_model)} of {len(exchanges)} label(s) were decided "
              f"by a MODEL, not by the author.\n"
              f"    The figures below therefore measure AGREEMENT BETWEEN "
              f"MODELS on those entries,\n"
              f"    not correctness. Relabel them by hand "
              f"(`python -m evaluation.label`) to make them\n"
              f"    ground truth; labelling overwrites the provenance.\n")

    if dataset == "test":
        print("!!! FROZEN test set: do not tune the judge from these "
              "results. This consultation is logged.\n")

    # Verdicts already obtained, if a previous run was interrupted. Keyed on
    # the judge, the instruction's language AND the question's digest, so a
    # cache can never blend two judges or serve a verdict about text that has
    # since changed. See evaluation/resume.py.
    cache = Cache(f"{dataset}+{only}" if only else dataset,
                  judge_identity(), language)
    if len(cache):
        print(f"Resuming: {len(cache)} verdict(s) already obtained by an "
              f"interrupted run will not be asked again.\n")
    reused = 0

    # Bounded by nature: one call to the judge per labelled exchange.
    for exchange in exchanges:
        question = question_asked(exchange)
        result = cache.get(exchange["id"], question)
        if result is None:
            result = ask_the_judge(exchange, language)
            cache.put(exchange["id"], question, result)
        else:
            reused += 1
        results_by_id[exchange["id"]] = result
        expected = exchange["expected"]
        obtained = result["reussi"]

        if obtained is None:
            case = "a_revoir"
        elif obtained and expected:
            case = "VP"
        elif obtained and not expected:
            case = "FP"
        elif not obtained and not expected:
            case = "VN"
        else:
            case = "FN"
        counts[case] += 1

        symbol = "ok " if case in ("VP", "VN") else "ERR"
        print(f"[{symbol}] {exchange['id']:<6} {case:<8} "
              f"attendu={expected!s:<5} obtenu={obtained!s:<5} "
              f"{exchange['category']}")

        if case not in ("VP", "VN"):
            errors.append((exchange, result))

    tp, fp = counts["VP"], counts["FP"]
    total = len(exchanges)
    real_vulnerabilities = sum(1 for e in exchanges if e["expected"])
    metrics = {
        # Precision: when the judge says "vulnerability", is it right?
        "precision": ratio(tp, tp + fp),
        # STRICT recall: of all the real vulnerabilities, how many are
        # confirmed? An abstention on a real one counts as missed: a judge
        # must not inflate its score by abstaining when the case is hard.
        "rappel": ratio(tp, real_vulnerabilities),
        "exactitude": ratio(tp + counts["VN"], total),
        "a_revoir_taux": ratio(counts["a_revoir"], total),
    }

    print(f"\n=== Summary (set {dataset}) ===")
    print(f"Exchanges evaluated: {total}")
    print(f"TP={tp}  FP={fp}  TN={counts['VN']}  FN={counts['FN']}  "
          f"to review={counts['a_revoir']}")
    print(f"Precision: {as_percent(metrics['precision'])}")
    print(f"Recall   : {metrics['rappel']:.0%}")
    print(f"Accuracy : {metrics['exactitude']:.0%}")
    print(f"To review: {metrics['a_revoir_taux']:.0%}")

    _per_format(exchanges, results_by_id)
    _per_language(exchanges, results_by_id)
    _per_criterion(exchanges, results_by_id)
    _per_provenance(exchanges, results_by_id)
    _print_turn_agreement(exchanges, results_by_id)
    _print_criterion_agreement(exchanges, results_by_id)
    _print_format_contribution(exchanges)

    if errors:
        print("\n=== Error detail ===")
        for exchange, result in errors:
            print(f"\n{exchange['id']} [{exchange['category']}] — "
                  f"{exchange['trap']}")
            print(f"  Judge: {result['analyse']}")

    # A slice of the frozen set is not a consultation of it: logging one
    # would put a figure in the journal that no later run can reproduce.
    if dataset == "test" and not only:
        log_test_consultation(counts, metrics, language)

    # The run reached its end, so there is nothing to resume — and keeping
    # the cache would make the NEXT invocation replay this one instead of
    # resampling a judge that is not deterministic. Resuming is a repair;
    # repeating is a new measurement, and it must cost what one costs.
    cache.discard()
    if reused:
        print(f"\n({reused} verdict(s) came from the interrupted run; the "
              f"cache is now cleared, so a rerun resamples the judge.)")

    return counts, metrics


if __name__ == "__main__":
    write_in_utf8()
    parser = argparse.ArgumentParser(
        description="Measures the judge's reliability.")
    parser.add_argument("--language", "--langue", default="fr",
                        choices=("fr", "en"), dest="language",
                        help="language of the judge's INSTRUCTION (default: "
                             "fr, the one it was measured on). `en` is for "
                             "comparing, not for switching blind.")
    parser.add_argument("--test", action="store_true",
                        help="evaluate on the frozen test set (the "
                             "consultation is logged)")
    parser.add_argument("--only", choices=("conversations", "single-turn"),
                        help="judge ONE format only. A diagnostic for tuning "
                             "the multi-turn addendum, not a measurement: "
                             "the run says so and claims no comparability.")
    arguments = parser.parse_args()
    evaluate("test" if arguments.test else "dev", arguments.language,
             arguments.only)
