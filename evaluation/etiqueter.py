"""
evaluation/etiqueter.py — Labels the collected exchanges by hand.

Editing a_etiqueter.json by hand is slow and invites silent typos ("dev "
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
    python -m evaluation.etiqueter              # label what is left
    python -m evaluation.etiqueter --integrer   # pour the labelled into the corpus
"""

import argparse
import json
from pathlib import Path

FOLDER = Path(__file__).parent
TO_LABEL_FILE = FOLDER / "a_etiqueter.json"
CONVERSATIONS_FILE = FOLDER / "a_etiqueter_conversations.json"
CORPUS_FILE = FOLDER / "echanges_etiquetes.json"

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
    print("  p. passer cet échange    q. quitter (le travail est enregistré)")

    # Bounded by its exits: 'p' skips, 'q' quits. No hidden infinity.
    while True:
        entered = input("> ").strip().lower()
        if entered == "q":
            raise KeyboardInterrupt
        if entered == "p":
            return None
        if entered.isdigit() and 1 <= int(entered) <= len(options):
            return options[int(entered) - 1]
        print(f"Réponds par un nombre entre 1 et {len(options)}, ou p / q.")


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

    A missing harvest is not an error: `a_etiqueter.json` and
    `a_etiqueter_conversations.json` are working files, outside git, and we do
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


def _left_to_label(harvests):
    """How many entries still have no label, across both harvests."""
    return sum(1 for harvest in harvests for e in harvest["entrees"]
               if e["expected"] is None)


def label():
    harvests = _harvests()
    if not harvests:
        names = ", ".join(p.name for p, _ in SOURCES)
        print(f"Aucune récolte à étiqueter ({names} absents).",
              "Récolte d'abord :",
              "  python -m evaluation.collecter_echanges",
              "  python -m evaluation.collecter_conversations --cible demo",
              sep="\n")
        return

    exchanges = [e for harvest in harvests for e in harvest["entrees"]]
    remaining = [e for e in exchanges if e["expected"] is None]

    if not remaining:
        print("Tous les échanges sont déjà étiquetés. "
              "Lance --integrer pour les verser dans le corpus.")
        return

    print(f"{len(remaining)} échange(s) à étiqueter sur {len(exchanges)}.")
    print("L'avis de l'arbitre n'est pas affiché : c'est voulu.")

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
                "Le chatbot a-t-il enfreint ses règles ?",
                ["non — pas de faille", "oui — faille"],
            )
            if verdict is None:
                continue

            category = ask_choice("Catégorie de piège ?", CATEGORIES)
            if category is None:
                continue

            group = exchange["group"]
            if group in set_of_group:
                dataset = set_of_group[group]
                print(f"\nJeu : {dataset} (imposé par le groupe {group}).")
            else:
                dataset = ask_choice(
                    "Quel jeu ? (dev = pour régler l'arbitre, "
                    "test = gelé, pour mesurer)",
                    ["dev", "test"],
                )
                if dataset is None:
                    continue
                set_of_group[group] = dataset

            print("\nEn une phrase, ce que ce cas teste (vide = la provenance) :")
            trap = input("> ").strip() or exchange.get("source", "")

            exchange["expected"] = verdict.startswith("oui")
            exchange["category"] = category
            exchange["dataset"] = dataset
            exchange["trap"] = trap

            # Saved after EVERY exchange: an interruption never loses the work
            # already done.
            save(file_of[id(exchange)], data_of[id(exchange)])
            print(f"-> {exchange['id']} enregistré.")

    except KeyboardInterrupt:
        print("\n\nInterrompu. Le travail déjà fait est enregistré.")

    labelled = sum(1 for e in exchanges if e["expected"] is not None)
    print(f"\n{labelled}/{len(exchanges)} échange(s) étiqueté(s).")
    if labelled == len(exchanges):
        print("Terminé : lance --integrer pour les verser dans le corpus.")


def integrate():
    """Pours the labelled exchanges into echanges_etiquetes.json."""
    harvests = _harvests()
    corpus = load(CORPUS_FILE)

    ready = [e for harvest in harvests for e in harvest["entrees"]
             if e["expected"] is not None]
    if not ready:
        print("Aucun échange étiqueté à intégrer.")
        return

    already = {e["id"] for e in corpus["exchanges"]}
    # A group already present in the corpus imposes its set: we refuse rather
    # than silently create a leak between the dev and test sets.
    set_of_group = {e["group"]: e["dataset"] for e in corpus["exchanges"]}

    added = 0
    for exchange in ready:
        if exchange["id"] in already:
            print(f"{exchange['id']} : déjà dans le corpus, ignoré.")
            continue
        expected = set_of_group.get(exchange["group"])
        if expected and expected != exchange["dataset"]:
            print(f"{exchange['id']} : le groupe {exchange['group']} est "
                  f"déjà en '{expected}', pas en '{exchange['dataset']}'. Ignoré.")
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
    print(f"{added} échange(s) ajouté(s) au corpus "
          f"({len(corpus['exchanges'])} au total, dont {multiturn} "
          f"conversation(s)).")
    if multiturn:
        # The judge cannot read a conversation yet: saying so here avoids
        # believing the evaluation took them into account.
        print("Les conversations ne sont PAS encore mesurées : la consigne "
              "de l'arbitre attend un seul tour. `evaluer_arbitre` les "
              "ignore et le signale.")

    # Counted AFTER the harvests were rewritten, so it reflects what is left.
    # This line used to read `restants`, a local of `label()`: `--integrer`
    # therefore ended on a NameError, after having written the corpus. The
    # data was safe and the message was lost — a crash on the last line of the
    # one command the author runs over a whole labelling session. No test
    # covered this file; it was found by reading it.
    left = _left_to_label(_harvests())
    if left:
        print(f"{left} échange(s) restent à étiqueter.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étiqueter à la main les échanges collectés.")
    parser.add_argument("--integrer", action="store_true",
                        help="verser les échanges étiquetés dans le corpus")
    arguments = parser.parse_args()
    integrate() if arguments.integrer else label()
