"""
evaluation/evaluer_arbitre.py — Measures the judge's reliability (Phase 2).

The principle: we give the judge exchanges whose right answer we ALREADY know
(labelled by hand in echanges_etiquetes.json), then count its mistakes.
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
           journal_test.jsonl: the discipline becomes verifiable.

Run it from the project root with:
    python -m evaluation.evaluer_arbitre            # the development set
    python -m evaluation.evaluer_arbitre --test     # the frozen test set
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from agents.arbitre import judge
from config import JUDGE_PROFILE, PROFILES

EXCHANGES_FILE = Path(__file__).parent / "echanges_etiquetes.json"
TEST_LOG = Path(__file__).parent / "journal_test.jsonl"


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
                f"Le groupe {group} est réparti entre 'dev' et 'test' "
                f"({exchange['id']}) : fuite entre les deux jeux."
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
        print(f"{ignored} conversation(s) multi-tours ignorée(s) : "
              f"l'arbitre ne sait juger qu'un seul tour (phase 3b).\n")
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


def evaluate(dataset="dev", language="fr"):
    exchanges = load_exchanges(dataset)
    counts = {"VP": 0, "FP": 0, "VN": 0, "FN": 0, "a_revoir": 0}
    errors = []

    print(f"Juge : profil {JUDGE_PROFILE}, "
          f"modèle {PROFILES[JUDGE_PROFILE]['model']}\n")

    if dataset == "test":
        print("!!! Jeu de TEST gelé : ne règle pas l'arbitre d'après ces "
              "résultats. Cette consultation est journalisée.\n")

    # Bounded by nature: one call to the judge per labelled exchange.
    for exchange in exchanges:
        result = judge(exchange["payload"], exchange["reply"], language)
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

    print(f"\n=== Bilan (jeu {dataset}) ===")
    print(f"Échanges évalués : {total}")
    print(f"VP={tp}  FP={fp}  VN={counts['VN']}  FN={counts['FN']}  "
          f"à revoir={counts['a_revoir']}")
    print(f"Précision : {metrics['precision']:.0%}")
    print(f"Rappel    : {metrics['rappel']:.0%}")
    print(f"Exactitude: {metrics['exactitude']:.0%}")
    print(f"À revoir  : {metrics['a_revoir_taux']:.0%}")

    if errors:
        print("\n=== Détail des erreurs ===")
        for exchange, result in errors:
            print(f"\n{exchange['id']} [{exchange['category']}] — {exchange['trap']}")
            print(f"  Juge : {result['analyse']}")

    if dataset == "test":
        log_test_consultation(counts, metrics, language)

    return counts, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mesure la fiabilité de l'arbitre.")
    parser.add_argument("--langue", default="fr", choices=("fr", "en"),
                         help="langue de la CONSIGNE du juge (défaut : fr, "
                              "celle sur laquelle il a été mesuré). `en` sert "
                              "à comparer, pas à basculer à l'aveugle.")
    parser.add_argument("--test", action="store_true",
                         help="évaluer sur le jeu de test gelé (consultation journalisée)")
    arguments = parser.parse_args()
    evaluate("test" if arguments.test else "dev", arguments.language)
