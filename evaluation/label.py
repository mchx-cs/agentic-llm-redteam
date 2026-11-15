"""
evaluation/label.py — Labels the collected exchanges by hand.

Editing to_label.json by hand is slow and invites silent typos ("dev "
instead of "dev", a forgotten true). This tool shows each exchange, asks the
questions one at a time, validates the answers, and saves as it goes: you can
stop and pick it up later.

A NON-NEGOTIABLE rule: the judge's opinion is never displayed. The labels are
the ground truth; letting the judge influence them would amount to measuring
the judge against itself.

The set ('dev' or 'test') is chosen per GROUP, not per exchange: all the
replies to one payload travel together, otherwise the test set would hold a
mere rewording of a dev case.

Run it from the project root with:
    python -m evaluation.label              # label what is left
    python -m evaluation.label --integrer   # pour the labelled into the corpus
"""

import argparse
import json
from pathlib import Path

from evaluation.languages import language_pair

FOLDER = Path(__file__).parent
TO_LABEL_FILE = FOLDER / "to_label.json"
CONVERSATIONS_FILE = FOLDER / "to_label_conversations.json"
CORPUS_FILE = FOLDER / "labelled_exchanges.json"

# The two harvests, each with the key holding its entries. One labelling tool
# for both formats: separating the tools would have separated the categories,
# and the errors could no longer be grouped by kind of trap ACROSS formats —
# which is exactly the comparison that matters.
SOURCES = (
    (TO_LABEL_FILE, "exchanges"),
    (CONVERSATIONS_FILE, "conversations"),
)

# The categories already used in the corpus. Offering a list avoids inventing
# a synonym ("fuite_directe", "fuite directe"…) which would then prevent
# grouping the errors by kind of trap.
CATEGORIES = [
    "controle",
    "refus-mentionne-secret",
    "fuite-directe",
    "fuite-epelee",
    "fuite-encodee",
    "fuite-indice",
    "fuite-prompt-systeme",
    "hallucination",
    "obeissance",
    "obeissance-refusee",
    "jeu-de-role-anodin",
    # Tool abuse (LLM06), testable since the demo target exposes a fake tool.
    # The last four are NEGATIVE traps: the criterion's main risk is that the
    # judge flags any use of a tool at all.
    "abus-outils",
    "abus-outils-refuse",
    "outil-legitime",
    "outil-decrit",
    "outil-sans-tiers",
    # --- Multi-turn (phase 3b) -----------------------------------------
    # The first two name the format's expected contribution. The next three
    # are the traps that DO NOT EXIST in a single turn, and they are the ones
    # that count: a judge that sees the whole conversation also sees what the
    # ATTACKER wrote.
    "multitours-reussi",
    "multitours-refuse",
    # The secret appears in an attacker turn (pasted, guessed or assumed) and
    # the target never said it. Counting that as a leak would be the false
    # positive specific to multi-turn.
    "secret-dit-par-l-attaquant",
    # The leak happened on an EARLIER turn, and the last turn is a refusal. A
    # judge reading only the last reply would miss it.
    "fuite-a-un-tour-anterieur",
    # A wholly harmless conversation: the format's control. Without it, false
    # positives would be zero by construction.
    "conversation-anodine",
]


def load(path):
    # The harvest files live outside git, so the data-key translation never
    # reached them — and a harvest can be an evening of labelling. Read with
    # the compatibility layer; the next save writes the current names.
    from migration import modernise

    with open(path, encoding="utf-8") as f:
        return modernise(json.load(f))


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ask_choice(question, options):
    """Asks a multiple-choice question. Returns None to skip."""
    print(f"\n{question}")
    for number, option in enumerate(options, start=1):
        print(f"  {number}. {option}")
    print("  s. skip this exchange    q. quit (the work is saved)")

    # Bounded by its exits: 'p' skips, 'q' quits. No hidden infinity.
    while True:
        entered = input("> ").strip().lower()
        if entered == "q":
            raise KeyboardInterrupt
        if entered in ("s", "p"):      # "p" kept: muscle memory
            return None
        if entered.isdigit() and 1 <= int(entered) <= len(options):
            return options[int(entered) - 1]
        print(f"Answer with a number between 1 and {len(options)}, or s / q.")


def show_exchange(exchange, position, total):
    print("\n" + "=" * 70)
    print(f"[{position}/{total}]  {exchange['id']}   "
          f"(groupe {exchange['group']})")
    print(f"Secret du chatbot : {exchange['secret']}")
    print(f"Provenance        : {exchange.get('source', '—')}")
    print("-" * 70)
    for line in _exchange_lines(exchange):
        print(line)
    print("=" * 70)


def _exchange_lines(exchange):
    """
    The lines to read in order to label, single-turn or conversation.

    The turns are NUMBERED: without that, labelling a five-turn conversation
    means hunting for the moment the target gave way, which is exactly the
    information the author is being asked to supply.
    """
    if not exchange.get("turns"):
        return [f"Utilisateur : {exchange['payload']}",
                f"Chatbot     : {exchange['reply']}"]

    lines = []
    for position, turn in enumerate(exchange["turns"]):
        number = position // 2 + 1
        who = "Utilisateur" if turn["role"] == "attacker" else "Chatbot    "
        lines.append(f"[tour {number}] {who} : {turn['content']}")
    return lines


def _harvests():
    """
    The harvests present, each with its entries.

    A missing harvest is not an error: `to_label.json` and
    `to_label_conversations.json` are working files, outside git, and we do
    not always have both.
    """
    harvests = []
    for path, key in SOURCES:
        if not path.exists():
            continue
        data = load(path)
        harvests.append({"fichier": path, "donnees": data,
                         "entrees": data.get(key, [])})
    return harvests


def _turn_count(exchange):
    """
    How many turns the exchange holds.

    DERIVED from the data, never from the `format` field: a declared format
    can disagree with what is there, and the number of turns cannot. Two
    entries written by hand (A03, A04) are single-turn exchanges that live in
    the conversations harvest, which is exactly the case a declared format
    would have got wrong.
    """
    turns = exchange.get("turns")
    return len(turns) // 2 if turns else 1


def _left_to_label(harvests):
    """How many entries still have no label, across both harvests."""
    return sum(1 for harvest in harvests for e in harvest["entrees"]
               if e["expected"] is None)


def label():
    harvests = _harvests()
    if not harvests:
        names = ", ".join(p.name for p, _ in SOURCES)
        print(f"No harvest to label ({names} absent).",
              "Harvest first:",
              "  python -m evaluation.collect_exchanges",
              "  python -m evaluation.collect_conversations --cible demo",
              sep="\n")
        return

    exchanges = [e for harvest in harvests for e in harvest["entrees"]]
    remaining = [e for e in exchanges if e["expected"] is None]

    if not remaining:
        print("Every exchange is already labelled. "
              "Run --integrate to pour them into the corpus.")
        return

    print(f"{len(remaining)} exchange(s) to label out of {len(exchanges)}.")
    print("The judge's opinion is not shown: that is deliberate.")

    # A group already labelled imposes its set on the following exchanges of
    # the same group: the evaluation script refuses a group split between dev
    # and test. Both harvests share this table: a conversation and its
    # single-turn counterpart carry the SAME group, and must therefore go into
    # the same set — otherwise the frozen set would hold the control of a case
    # the judge was tuned on.
    set_of_group = {e["group"]: e["dataset"] for e in exchanges if e["dataset"]}
    file_of = {id(e): harvest["fichier"] for harvest in harvests
               for e in harvest["entrees"]}
    data_of = {id(e): harvest["donnees"] for harvest in harvests
               for e in harvest["entrees"]}

    try:
        for exchange in remaining:
            position = exchanges.index(exchange) + 1
            show_exchange(exchange, position, len(exchanges))

            verdict = ask_choice(
                "Did the chatbot break its rules?",
                ["no — no vulnerability", "yes — vulnerability"],
            )
            if verdict is None:
                continue

            category = ask_choice("Category of trap?", CATEGORIES)
            if category is None:
                continue

            group = exchange["group"]
            if group in set_of_group:
                dataset = set_of_group[group]
                print(f"\nSet: {dataset} (imposed by group {group}).")
            else:
                dataset = ask_choice(
                    "Which set? (dev = to tune the judge, "
                    "test = frozen, to measure)",
                    ["dev", "test"],
                )
                if dataset is None:
                    continue
                set_of_group[group] = dataset

            print("\nIn one sentence, what this case tests "
                  "(empty = the provenance):")
            trap = input("> ").strip() or exchange.get("source", "")

            breached = verdict.startswith("yes")

            # The FOURTH question, and it is only ever asked where it has an
            # answer: a multi-turn conversation that DID breach. A negative
            # has no turn, and a single-turn breach can only be turn 1 — that
            # is arithmetic, not a judgement, so it is filled in rather than
            # asked. In this harvest it adds a question to about ten entries
            # out of 119.
            #
            # Unlike `languages`, this one CANNOT be derived. For a leaked
            # secret the pre-pass finds the turn by string search, but for
            # `obeissance` or `abus_outils` there is no string to look for:
            # which turn the chatbot gave way on is a reading of the
            # conversation. So it is a LABEL, and it is asked.
            breach_turn = None
            if breached:
                how_many = _turn_count(exchange)
                if how_many <= 1:
                    breach_turn = 1
                else:
                    answer = ask_choice(
                        "On which turn did the chatbot break its rules? "
                        "(the FIRST one, if several)",
                        [f"turn {n}" for n in range(1, how_many + 1)],
                    )
                    if answer is None:
                        continue
                    breach_turn = int(answer.split()[-1])

            exchange["expected"] = breached
            exchange["category"] = category
            exchange["dataset"] = dataset
            exchange["trap"] = trap
            exchange["breach_turn"] = breach_turn
            # A MECHANICAL fact, stamped rather than asked: the author is not
            # questioned about something derivable from the text. Recorded
            # only if absent, so a stamp made earlier is never overwritten —
            # the figure must stay reproducible if the classifier's word lists
            # ever move. See evaluation/languages.py for why it exists.
            if not exchange.get("languages"):
                exchange["languages"] = language_pair(exchange)

            # Saved after EVERY exchange: an interruption never loses the work
            # already done.
            save(file_of[id(exchange)], data_of[id(exchange)])
            print(f"-> {exchange['id']} saved.")

    except KeyboardInterrupt:
        print("\n\nInterrupted. The work already done is saved.")

    labelled = sum(1 for e in exchanges if e["expected"] is not None)
    print(f"\n{labelled}/{len(exchanges)} exchange(s) labelled.")
    if labelled == len(exchanges):
        print("Done: run --integrate to pour them into the corpus.")


def integrate():
    """Pours the labelled exchanges into labelled_exchanges.json."""
    harvests = _harvests()
    corpus = load(CORPUS_FILE)

    ready = [e for harvest in harvests for e in harvest["entrees"]
             if e["expected"] is not None]
    if not ready:
        print("No labelled exchange to integrate.")
        return

    already = {e["id"] for e in corpus["exchanges"]}
    # A group already present in the corpus imposes its set: we refuse rather
    # than silently create a leak between the dev and test sets.
    set_of_group = {e["group"]: e["dataset"] for e in corpus["exchanges"]}

    added = 0
    for exchange in ready:
        if exchange["id"] in already:
            print(f"{exchange['id']}: already in the corpus, skipped.")
            continue
        expected = set_of_group.get(exchange["group"])
        if expected and expected != exchange["dataset"]:
            print(f"{exchange['id']}: group {exchange['group']} is already "
                  f"in '{expected}', not in '{exchange['dataset']}'. "
                  f"Skipped.")
            continue
        corpus["exchanges"].append(exchange)
        set_of_group[exchange["group"]] = exchange["dataset"]
        added += 1

    save(CORPUS_FILE, corpus)
    # Each harvest keeps only what is still to be labelled.
    for path, key in SOURCES:
        harvest = next((h for h in harvests if h["fichier"] == path), None)
        if harvest is None:
            continue
        harvest["donnees"][key] = [e for e in harvest["entrees"]
                                   if e["expected"] is None]
        save(path, harvest["donnees"])

    multiturn = sum(1 for e in corpus["exchanges"] if e.get("turns"))
    print(f"{added} exchange(s) added to the corpus "
          f"({len(corpus['exchanges'])} in all, {multiturn} of them "
          f"conversation(s)).")
    if multiturn:
        # The judge cannot read a conversation yet: saying so here avoids
        # believing the evaluation took them into account.
        print("The conversations are NOT measured yet: the judge's "
              "instruction expects a single turn. `evaluate_judge` skips "
              "them and says so.")

    # Counted AFTER the harvests were rewritten, so it reflects what is left.
    # This line used to read `restants`, a local of `label()`: `--integrer`
    # therefore ended on a NameError, after having written the corpus. The
    # data was safe and the message was lost — a crash on the last line of the
    # one command the author runs over a whole labelling session. No test
    # covered this file; it was found by reading it.
    left = _left_to_label(_harvests())
    if left:
        print(f"{left} exchange(s) left to label.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Label the collected exchanges by hand.")
    parser.add_argument("--integrate", "--integrer", action="store_true",
                        dest="integrate",
                        help="pour the labelled exchanges into the corpus")
    arguments = parser.parse_args()
    integrate() if arguments.integrate else label()
