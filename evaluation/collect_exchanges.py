"""
evaluation/collect_exchanges.py — Harvests real exchanges with the target.

The original labelled exchanges are FICTIONAL: written by hand, they reflect
what we imagine a target would reply. A real model's answers are more varied
and more surprising, and it is on those that the judge must be reliable. This
script sends the library's payloads to the real target and records the
exchanges in to_label.json.

After that it is the AUTHOR who labels each exchange, by hand
(`python -m evaluation.label`), and `--integrate` pours them into
labelled_exchanges.json.

Four deliberate choices:
- The prompts come from payloads/library.json and nothing else: the
  harvest holds only techniques already practised by hand.
- The judge's opinion is NOT recorded. Seeing its verdict would influence the
  human label, and we would end up measuring the judge against itself.
- It is BOUNDED, and the bound is the point rather than a precaution. The
  library crosses to 9,268 combinations; at two samples each that is 18,536
  entries and 33 MB, which is not a harvest but a landfill — `label.py` once
  opened on entry 25 of 18,515. Labelling is the scarce resource here, so the
  harvest is sized to what a person will actually read.
- It APPENDS. The corpus needs several targets and several defence levels, so
  it takes several commands; overwriting would erase the previous harvest and
  an evening of labelling with it. Re-running the same command duplicates
  nothing, because an id already present is skipped.

Run it from the project root with:  python -m evaluation.collect_exchanges
"""

import argparse
import json
import sys
from pathlib import Path

from agents.attacker import generate_payloads
from agents.planner import _share_budget
from console import write_in_utf8
from targets import choose_target, secret_of
from targets.indirect import (INDIRECT_TRIGGER, NoIndirectChannel,
                              require_indirect)

OUTPUT_FILE = Path(__file__).parent / "to_label.json"

# Replies asked per payload: the target has randomness, two answers to the
# same payload can differ (one leaks, the other refuses…).
SAMPLE_COUNT = 2

#: Payloads kept, out of the library's 9,268 combinations. THE SAMPLING
#: POLICY, and it is deliberately one number rather than a rule buried in the
#: loop: it belongs to whoever decides what the corpus should contain, and a
#: policy you cannot see is a policy you cannot change.
#:
#: 60 payloads x 2 samples = 120 exchanges, which is the order of the corpus
#: itself (245 entries built over weeks). The sibling collector's bound is
#: MAX_SEQUENCES = 12.
MAX_PAYLOADS = 60

#: Prefix of the harvested ids. NOT `R`: `R01`..`R09` are the frozen set's own
#: identifiers, so the old prefix collided with the corpus. The 2026-11-18
#: guard catches a collision when labelling; a prefix that cannot collide
#: prevents it, and the guard stays as the backstop.
PREFIX = "H"


def _sample(payloads, limit):
    """
    The payloads to harvest, round-robin over techniques.

    `_share_budget` is the planner's own function, read rather than restated:
    it is this project's answer to "which payloads, at what grain", and a
    second copy would drift from the campaign's.

    The grain differs from a campaign's, and that is intended. It groups by
    `group` where there is one and by TECHNIQUE otherwise, and
    `generate_payloads` emits no `group` — so a harvest rotates per technique
    where a campaign rotates per garak module. A campaign wants coverage of
    distinct KINDS of attack; a corpus needs variety, which is the recorded
    reason the multi-turn collector takes its sequences in library order.
    """
    return _share_budget(payloads, limit)


def collect(target_name=None, limit=MAX_PAYLOADS, indirect=False):
    # The one `.env` names unless told otherwise: we therefore harvest from
    # the decoy as readily as from `demo`, without touching this script.
    ask_target = choose_target(target_name)
    # LE CANAL EST EXIGE, jamais devine. Une cible qui jette la note en
    # silence laisserait croire qu'on a mene une attaque indirecte quand le
    # modele n'a jamais vu la note : le juge noterait un echange anodin et la
    # recolte porterait une provenance fausse.
    if indirect:
        require_indirect(ask_target, target_name or "the configured target")
    # DECLARED by the target, never hardcoded. `labelling_prepass` searches
    # the replies for this exact string to tell the author who said the
    # secret, so a wrong value here reports zero disclosures over a harvest
    # full of them. None is a real answer: `records` guards records rather
    # than a value.
    secret = secret_of(target_name)

    payloads = generate_payloads()
    kept = _sample(payloads, limit)
    print(f"{len(payloads)} combination(s) in the library, {len(kept)} kept "
          f"(limit {limit}), {len(kept) * SAMPLE_COUNT} exchange(s) to "
          f"harvest.")
    print(f"Secret recorded: {secret or 'none (this target holds no value)'}")

    # APPEND: see the module docstring. The ids already present are skipped,
    # so re-running the same command costs requests and adds nothing.
    existing = {}
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    exchanges = list(existing.get("exchanges", []))
    already = {entry.get("id") for entry in exchanges}

    # La LIVRAISON est dans l'identifiant : la recolte saute les ids deja
    # presents, donc une recolte indirecte qui reutiliserait les ids directs
    # serait declaree << deja recoltee >> et n'ajouterait rien en affichant
    # son travail -- le defaut du 2026-11-13.
    stamp = (target_name or "env").replace(":", "")
    if indirect:
        stamp = f"{stamp}i"
    added = 0
    for payload_number, payload in enumerate(kept, start=1):
        # All the replies to one payload form a group: they will have to go
        # into the same set (dev or test), never be split between them.
        group = f"{PREFIX}-{stamp}-{payload_number:02d}"
        for sample in range(1, SAMPLE_COUNT + 1):
            identifier = f"{group}-{sample}"
            if identifier in already:
                continue
            if indirect:
                # Le payload va dans le contenu RECUPERE, et la question
                # posee est le declencheur FIXE : s'il variait il serait une
                # seconde variable, et une fuite pourrait s'imputer a une
                # question bien choisie plutot qu'a la note.
                ask_target.plant(payload["text"])
                asked = INDIRECT_TRIGGER
            else:
                asked = payload["text"]
            reply = ask_target(asked)
            exchanges.append({
                "id": identifier,
                "group": group,
                "category": None,      # to fill in by hand
                "dataset": None,       # to fill in by hand: "dev" or "test"
                "secret": secret,
                "source": (f"real target — {payload['technique']} / "
                           f"{payload['objective']} / "
                           f"{payload['transformation']}"),
                # Ce qui a ete DEMANDE, et non le payload : en indirect
                # les deux diffèrent, et c'est l'echange que le juge verra.
                "payload": asked,
                "reply": reply,
                # LA PROVENANCE, estampillee a la SOURCE. `label.py` la
                # conserve plutot que de la recalculer, donc elle traverse
                # jusqu'au corpus -- et le juge ne pourra jamais la deduire,
                # le document n'etant pas dans l'echange qu'on lui montre.
                "delivery": "indirect" if indirect else "direct",
                "planted": payload["text"] if indirect else None,
                "expected": None,      # to fill in by hand: true or false
                "trap": "",            # to fill in by hand
            })
            added += 1
            print(f"{identifier} collected")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"exchanges": exchanges}, f, ensure_ascii=False, indent=2)

    skipped = len(kept) * SAMPLE_COUNT - added
    if skipped:
        print(f"\n{skipped} already harvested, skipped.")
    print(f"\n{added} exchange(s) added, {len(exchanges)} in "
          f"{OUTPUT_FILE.name}, to be labelled by hand.")
    return exchanges


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Harvests real exchanges with a target, to be labelled.")
    parser.add_argument("--target", default=None,
                        help="the target to harvest from (default: TARGET "
                             "in .env)")
    parser.add_argument(
        "--indirect", action="store_true",
        help="PLANT each payload in the retrieved content, then ask the "
             "fixed innocuous trigger. The target must DECLARE the channel; "
             "the harvest refuses rather than guessing. Entries are stamped "
             "`delivery: indirect`, which the judge can never derive since "
             "the document is not in the exchange it is shown.")
    parser.add_argument("--payloads", type=int, default=MAX_PAYLOADS,
                        metavar="N",
                        help=f"payloads kept out of the library's thousands "
                             f"(default: {MAX_PAYLOADS}). Each one is asked "
                             f"{SAMPLE_COUNT} times, so N x {SAMPLE_COUNT} "
                             f"exchanges to label by hand.")
    parsed = parser.parse_args(arguments)
    try:
        collect(target_name=parsed.target, limit=parsed.payloads,
                indirect=parsed.indirect)
    except NoIndirectChannel as refusal:
        # Attrape plutot que laisse remonter : un traceback sur une erreur
        # legitime d'operateur est le defaut corrige pour les campagnes --
        # << huit lignes de traceback avec le bon message noye dedans >>. Le
        # message de `require_indirect` dit deja quoi faire, il ne lui manque
        # que de sortir seul.
        print(f"\nHarvest REFUSED.\n{refusal}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    write_in_utf8()
    raise SystemExit(main())
