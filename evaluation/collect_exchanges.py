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
import hashlib
import json
import sys
from pathlib import Path

from agents.attacker import generate_payloads, load_library
from evaluation.collect_conversations import targeted_objectives
from agents.planner import _share_budget, grain_of
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


def _grain(payload):
    """
    The harvest's grain: the campaign's, PLUS the objective.

    WHY IT DIFFERS, and it was measured by running it. The harvest of
    2026-11-27 kept twelve payloads and all twelve carried `refus-1`:
    `_share_budget` groups by module, so the first of each group shares one
    objective, and the other two the reconnaissance had derived were never
    exercised.

    A campaign wants each KIND of attack swept — that grain is measured, and
    it does not move. A CORPUS wants each objective exercised, because an
    objective is a different thing the target protects, and a corpus that
    holds only one of them measures the judge on one subject.

    The default is READ from the planner rather than restated: a second copy
    would drift from the campaign's on the first adjustment.
    """
    return (grain_of(payload), payload.get("objective"))


def _sample(payloads, limit):
    """
    The payloads to harvest, round-robin over (technique, objective).

    `_share_budget` is the planner's own function, read rather than restated:
    it is this project's answer to "which payloads, at what grain", and a
    second copy would drift from the campaign's. Only the KEY differs, and
    `_grain` says why.
    """
    return _share_budget(payloads, limit, key=_grain)



def _tag(objective_id):
    """
    L'objectif, reduit a ce qui tient dans un identifiant.

    `None` est le cas des payloads COMPLETS joues seuls : ils portent leur
    propre intention et ne croisent pas l'axe des objectifs. `bare` le dit,
    la ou une chaine vide donnerait un double tiret illisible.

    POUR LA LISIBILITE SEULEMENT : ce tag n'identifie RIEN. La
    reconnaissance renumerote les sujets refuses a chaque run, donc `refus-1`
    designe un sujet different d'une recolte a l'autre -- verifie le
    2026-11-27 sur deux entrees de meme id et de libelles differents.
    L'identite est portee par `_digest`.
    """
    if not objective_id:
        return "bare"
    return "".join(c for c in str(objective_id) if c.isalnum()).lower()


def _digest(text):
    """
    Ce qui IDENTIFIE un payload : un condense de son texte.

    Pourquoi pas une position. L'id portait
    `H-<cible>-<objectif>-<position>`, et la position est un index dans la
    liste echantillonnee : elle change de sens des que le grain du
    round-robin change. Le 2026-11-27, passer au grain par objectif a fait
    designer par `refus1-04` un payload different de celui deja dans le
    corpus sous ce nom -- et `label.py`, qui refuse un id deja present sans
    regarder le contenu, l'a rendu INJOIGNABLE pour l'etiquetage, en silence.

    Un condense est stable a travers les grains, les renumerotations
    d'objectifs et les reordonnancements de bibliotheque. << Deja recolte >>
    veut alors dire ce qu'on veut qu'il dise : le meme payload, contre la
    meme cible, par la meme livraison.

    Douze hexadecimaux : assez pour que deux payloads d'une meme recolte ne
    collisionnent pas (le catalogue en compte ~9 300, et la probabilite est
    de l'ordre de 10^-9), assez court pour qu'un id reste lisible.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def collect(target_name=None, limit=MAX_PAYLOADS, indirect=False,
            harmless=False):
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

    # LES OBJECTIFS VIENNENT DE LA RECONNAISSANCE, pas de la bibliotheque.
    # Les trois generiques (`presentation`, `mission`, `culture-generale`)
    # sont tous ANODINS, donc une recolte qui les garde ne demande jamais ce
    # que la cible protege et ses entrees sont des negatives par
    # construction. C'est le defaut corrige le 2026-11-13 pour le collecteur
    # de CONVERSATIONS seulement.
    #
    # La logique est LUE chez le voisin et non recopiee : son repli sur
    # l'objectif anodin, sa borne et son ANNONCE de ce repli ne doivent
    # exister qu'une fois.
    objectives, summary = targeted_objectives(ask_target, load_library(),
                                              harmless)
    print(f"Objectives: {summary}")
    payloads = generate_payloads(objectives)
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
        # L'OBJECTIF EST DANS L'ID. Le numero de payload est un index dans
        # la liste echantillonnee, et cette liste change avec les objectifs :
        # sans ce tag, relancer avec de nouveaux objectifs produirait les
        # memes ids pour des payloads DIFFERENTS, que la recolte sauterait en
        # les declarant deja recoltes.
        tag = _tag(payload["objective"])
        group = f"{PREFIX}-{stamp}-{tag}-{_digest(payload['text'])}"
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
    parser.add_argument(
        "--harmless", "--anodin", action="store_true",
        help="keep the library's HARMLESS objectives instead of running "
             "reconnaissance. For harvesting NEGATIVES: a corpus with no "
             "inoffensive exchange has zero false positives by "
             "construction, which the OWASP manual names as the "
             "all-malicious corpus trap.")
    parser.add_argument("--payloads", type=int, default=MAX_PAYLOADS,
                        metavar="N",
                        help=f"payloads kept out of the library's thousands "
                             f"(default: {MAX_PAYLOADS}). Each one is asked "
                             f"{SAMPLE_COUNT} times, so N x {SAMPLE_COUNT} "
                             f"exchanges to label by hand.")
    parsed = parser.parse_args(arguments)
    try:
        collect(target_name=parsed.target, limit=parsed.payloads,
                indirect=parsed.indirect, harmless=parsed.harmless)
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
