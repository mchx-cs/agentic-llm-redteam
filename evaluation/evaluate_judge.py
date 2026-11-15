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

EXCHANGES_FILE = Path(__file__).parent / "labelled_exchanges.json"
TEST_LOG = Path(__file__).parent / "test_set_log.jsonl"

# The judge the published 89 / 100 / 96 were measured on. Any other model is
# a different measurement, not a check of this one — and the project has
# changed judge model before (llama3.2 -> gpt-oss-120b lifted recall from
# 50% to 100%), so this will happen again.
MEASURED_ON = "groq/openai/gpt-oss-120b"


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


def is_conversation(exchange):
    """
    Does this entry need the multi-turn instruction?

    DERIVED from the number of turns, never from the `format` field — a
    declared format can disagree with the data, and two hand-written entries
    (A03, A04) are single-turn exchanges living in the conversations harvest,
    which is exactly the case a declared format gets wrong.

    One turn means the SINGLE-TURN instruction, which is the frozen artefact:
    an entry stored as `turns` but holding one exchange must be judged by the
    same bytes as the 90 exchanges the 89 / 100 / 96 were measured on.
    """
    turns = exchange.get("turns")
    return bool(turns) and len(turns) > 2


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


def log_test_consultation(counts, metrics, language='fr'):
    """Appends a line to the log of frozen-set consultations."""
    entry = {
        "date": datetime.now().isoformat(timespec="seconds"),
        # Without the judge being measured, the log's lines would not be
        # comparable.
        "juge": f"{JUDGE_PROFILE}/{PROFILES[JUDGE_PROFILE]['model']}",
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
            "precision": ratio(tp, tp + fp),
            "rappel": ratio(tp, positives) if positives else None,
            "exactitude": ratio(tp + tn, len(exchanges))}


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
    current = f"{JUDGE_PROFILE}/{PROFILES[JUDGE_PROFILE]['model']}"
    same_judge = current == MEASURED_ON
    single_note = ("comparable with 89 / 100 / 96" if same_judge
                   else f"NOT comparable: those figures are "
                        f"{MEASURED_ON}, this is {current}")

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
        s = scores(subset, results_by_id)
        recall = (f"{s['rappel']:.0%}" if s["rappel"] is not None
                  else "n/a (no vulnerability)")
        print(f"  {name}  {s['n']:>3} exchange(s), {s['positives']:>2} "
              f"vulnerability(ies)  precision={s['precision']:.0%}  "
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


def evaluate(dataset="dev", language="fr"):
    exchanges = load_exchanges(dataset)
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

    # Bounded by nature: one call to the judge per labelled exchange.
    for exchange in exchanges:
        result = ask_the_judge(exchange, language)
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
    print(f"Precision: {metrics['precision']:.0%}")
    print(f"Recall   : {metrics['rappel']:.0%}")
    print(f"Accuracy : {metrics['exactitude']:.0%}")
    print(f"To review: {metrics['a_revoir_taux']:.0%}")

    _per_format(exchanges, results_by_id)
    _per_language(exchanges, results_by_id)
    _print_turn_agreement(exchanges, results_by_id)

    if errors:
        print("\n=== Error detail ===")
        for exchange, result in errors:
            print(f"\n{exchange['id']} [{exchange['category']}] — "
                  f"{exchange['trap']}")
            print(f"  Judge: {result['analyse']}")

    if dataset == "test":
        log_test_consultation(counts, metrics, language)

    return counts, metrics


if __name__ == "__main__":
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
    arguments = parser.parse_args()
    evaluate("test" if arguments.test else "dev", arguments.language)
