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

from agents.judge import judge
from config import JUDGE_PROFILE, PROFILES

EXCHANGES_FILE = Path(__file__).parent / "labelled_exchanges.json"
TEST_LOG = Path(__file__).parent / "test_set_log.jsonl"


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

    # The conversations (phase 3b) are in the corpus but NOT measurable
    # here: the judge's instruction expects a single turn, and its examples
    # are written that way. Giving them to it anyway would produce verdicts on
    # a format it does not know, and those verdicts would count in the
    # precision — so the first `--integrer` of conversations would silently
    # shift a reference measurement. We skip them, and we SAY SO: a corpus
    # that grows without the measurement changing needs explaining.
    single_turn = [e for e in in_dataset if not e.get("turns")]
    ignored = len(in_dataset) - len(single_turn)
    if ignored:
        print(f"{ignored} multi-turn conversation(s) skipped: the judge can "
              f"only score a single turn (phase 3b).\n")
    return single_turn


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


def evaluate(dataset="dev", language="fr"):
    exchanges = load_exchanges(dataset)
    counts = {"VP": 0, "FP": 0, "VN": 0, "FN": 0, "a_revoir": 0}
    errors = []
    results_by_id = {}

    print(f"Judge: profile {JUDGE_PROFILE}, "
          f"model {PROFILES[JUDGE_PROFILE]['model']}\n")

    if dataset == "test":
        print("!!! FROZEN test set: do not tune the judge from these "
              "results. This consultation is logged.\n")

    # Bounded by nature: one call to the judge per labelled exchange.
    for exchange in exchanges:
        result = judge(exchange["payload"], exchange["reply"], language)
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

    _per_language(exchanges, results_by_id)

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
