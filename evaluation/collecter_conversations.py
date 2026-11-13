"""
evaluation/collecter_conversations.py — Récolter de vraies conversations
multi-tours, à étiqueter à la main (phase 3b).

`collecter_echanges.py` récolte des échanges d'UN tour. L'arbitre ne sait
juger que ce format, et les 90 échanges du corpus le sont tous. Pour qu'il
apprenne à juger une conversation, il faut d'abord un corpus de
conversations — étiqueté à la main, par l'auteur, comme toujours. C'est ce
script qui en fournit la matière.

Pourquoi il est GRATUIT, et pourquoi ça compte
----------------------------------------------
Aucun modèle attaquant, aucun juge : les séquences sont fixes, et seule la
CIBLE est appelée. Contre `--cible demo`, qui tourne sur Ollama en local, la
récolte ne consomme donc aucun quota. C'est ce qui rend le corpus multi-tours
atteignable : l'offre gratuite du juge (200 000 tokens par jour) ne permettrait
pas de récolter ET de mesurer.

D'où viennent les séquences
---------------------------
Des mêmes ingrédients que la composition mono-tour : un payload complet de
garak sert de premier tour, et l'objectif issu de la reconnaissance fournit le
second (`attaquant.sequencer`). Rien n'est inventé pour l'occasion — on ne
récolte que des techniques déjà pratiquées par l'outil.

Conséquence utile : la variante mono-tour des mêmes ingrédients existe déjà
(`attaquant.composer`). `--comparer` récolte les deux, ce qui donne des paires
dont la seule différence est le nombre de tours. C'est la mesure qui tranchera
l'intérêt du multi-tours, et elle ne vaut que si les deux bras partagent leurs
ingrédients.

Deux règles héritées, non négociables
-------------------------------------
- **L'avis de l'arbitre n'est PAS enregistré.** Le voir influencerait
  l'étiquette humaine, et on mesurerait le juge contre lui-même.
- **Les échantillons d'une même séquence forment un GROUPE**, et un groupe
  ne se répartit jamais entre le jeu de développement et le jeu de test.

Lance-le depuis la racine du projet :
    python -m evaluation.collecter_conversations --cible demo
    python -m evaluation.collecter_conversations --cible demo --comparer
"""

import argparse
import json
from pathlib import Path

from agents.attaquant import charger_bibliotheque, composer, sequencer
from cibles import choose_target, is_bundled_target
from cibles.conversation import MAX_TURNS, require_conversation, play

FICHIER_SORTIE = Path(__file__).parent / "a_etiqueter_conversations.json"

# La cible a de l'aléa : deux fois la même séquence peut donner deux issues
# différentes (l'une cède, l'autre refuse). Les deux sont des cas utiles.
NB_ECHANTILLONS = 2

# Combien de séquences au plus. Borne explicite, comme toute boucle du
# projet : une récolte qui part sur 1 143 payloads × 2 échantillons
# occuperait la soirée et produirait un corpus qu'on n'étiquettera jamais.
MAX_SEQUENCES = 12

# Les objectifs génériques de la bibliothèque ne demandent rien de sensible
# (« te présenter en une phrase ») : ils servent de CONTRÔLE, et un corpus
# sans contrôles aurait des faux positifs nuls par construction — le piège
# que le manuel OWASP nomme explicitement.
OBJECTIF_CONTROLE = "presentation"

# Combien d'objectifs issus de la reconnaissance on fait tourner. Borné :
# une cible bavarde peut déclarer six sujets refusés, et croiser tout avec
# tout gonflerait une récolte qu'on n'étiquettera jamais.
MAX_OBJECTIFS = 3


def _objectifs(interroger_cible, bibliotheque, anodin=False):
    """
    Ce que le second tour va RÉCLAMER.

    Le problème qu'on corrige ici est structurel, et la première récolte l'a
    rendu visible : 3 positifs pour 61 négatifs. Les trois objectifs
    génériques de la bibliothèque (`presentation`, `mission`,
    `culture-generale`) sont tous ANODINS, donc le second tour ne demandait
    jamais ce que la cible protège. Mesurer le rappel d'un juge sur trois cas
    ne voudrait rien dire.

    Les objectifs qui réclament quelque chose viennent de la RECONNAISSANCE :
    `refus-N` pour chaque sujet que la cible dit refuser, `outil-N` pour
    chaque outil qu'elle déclare. C'est exactement ce qu'une campagne fait,
    et c'est gratuit — l'analyste tourne sur le profil actif, local par
    défaut.

    Avec `anodin`, on garde l'objectif de contrôle : un corpus a besoin de
    conversations entièrement inoffensives, sinon ses faux positifs sont nuls
    par construction.
    """
    generiques = {o["id"]: o for o in bibliotheque["objectifs"]}
    controle = (generiques.get(OBJECTIF_CONTROLE)
                or next(iter(generiques.values())))
    if anodin:
        return [controle], "objectif de contrôle (anodin)"

    from agents.planificateur import objectifs_pour
    from agents.reconnaissance import reconnaitre

    print("Reconnaissance de la cible (sondes anodines, modèle local)...")
    fiche = reconnaitre(interroger_cible)
    vises = [o for o in objectifs_pour(fiche, bibliotheque)
             if o.get("origine") == "reconnaissance"][:MAX_OBJECTIFS]

    if not vises:
        # Une cible qui ne déclare ni sujet refusé ni outil ne donne aucun
        # objectif ciblé. On le DIT : sans ça, la récolte repartirait sur
        # l'objectif anodin et on s'étonnerait de n'avoir aucun positif.
        print("/!\\ La cible ne déclare ni sujet refusé ni outil : aucun "
              "objectif ciblé. Récolte avec l'objectif anodin, qui ne "
              "produira presque que des négatifs.")
        return [controle], "objectif de contrôle (faute de mieux)"

    for objectif in vises:
        print(f"  objectif retenu : {objectif['id']} — "
              f"{objectif['formulation'][:70]}")
    return vises, f"{len(vises)} objectif(s) issus de la reconnaissance"


def _sequences(limite=MAX_SEQUENCES, objectifs=None):
    """
    Les séquences à jouer : (identifiant, messages, provenance).

    Un payload complet par technique, pas davantage : la diversité des
    techniques vaut mieux que plusieurs variantes de la même, exactement
    comme le tour de rôle d'une campagne.
    """
    bibliotheque = charger_bibliotheque()
    if not objectifs:
        generiques = {o["id"]: o for o in bibliotheque["objectifs"]}
        objectifs = [generiques.get(OBJECTIF_CONTROLE)
                     or next(iter(generiques.values()))]

    sequences = []
    for technique in bibliotheque["techniques"]:
        complets = technique.get("payloads_complets") or []
        if not complets:
            continue
        # Tour de rôle sur les objectifs : chaque séquence en reçoit UN, pour
        # que la taille de la récolte reste prévisible (séquences ×
        # échantillons) tout en variant ce qui est réclamé.
        objectif = objectifs[len(sequences) % len(objectifs)]
        sequences.append({
            "technique": technique["id"],
            "objectif": objectif["id"],
            "messages": sequencer(complets[0], objectif),
            "mono_tour": composer(complets[0], objectif),
        })
        if len(sequences) >= limite:
            break
    return sequences


def _fragment(texte):
    """Les caractères alphanumériques d'un identifiant, et rien d'autre."""
    return "".join(c for c in str(texte) if c.isalnum()) or "x"


def _etiquette(nom_cible):
    """
    Un fragment d'identifiant qui dit CONTRE QUOI la conversation a été
    récoltée (`demo`, `demo3`, `leurre`…).

    Sans lui, deux récoltes se marchent dessus : les niveaux 2 et 3 de la
    cible de démonstration REFUSENT, donc ils fournissent les négatifs d'un
    corpus que le niveau 1 remplirait de positifs. Il faut pouvoir récolter
    les trois, et donc que leurs identifiants diffèrent.
    """
    return _fragment(nom_cible or "env")


def collecter(nom_cible=None, comparer=False, limite=MAX_SEQUENCES,
              anodin=False):
    interroger_cible = choose_target(nom_cible)
    require_conversation(interroger_cible, nom_cible or "la cible configurée")
    etiquette = _etiquette(nom_cible)

    objectifs, resume = _objectifs(interroger_cible, charger_bibliotheque(),
                                   anodin)
    print(f"  -> {resume}\n")
    sequences = _sequences(limite, objectifs)
    if not sequences:
        raise SystemExit(
            "Aucune séquence : la bibliothèque n'a aucun payload complet.\n"
            "Synchronise l'instantané garak "
            "(python -m payloads.source_garak --version).")

    # On AJOUTE à la récolte existante au lieu de l'écraser. Un fichier de
    # travail qu'une seconde commande efface, c'est une soirée d'étiquetage
    # perdue — et récolter plusieurs niveaux de défense demande justement
    # plusieurs commandes.
    entrees = _recolte_existante()
    deja = {e["id"] for e in entrees}

    # Boucles bornées : séquences (liste finie) × NB_ECHANTILLONS.
    for numero, sequence in enumerate(sequences, start=1):
        # L'identifiant porte la cible ET l'objectif. Sans l'objectif, une
        # récolte relancée avec un objectif différent retombait sur les mêmes
        # identifiants, les trouvait « déjà récoltés » et les SAUTAIT : la
        # commande semblait avoir travaillé alors que le nouvel objectif
        # n'avait jamais été envoyé. Trouvé en comparant ce que la récolte
        # annonçait à ce qu'elle contenait.
        groupe = (f"C-{etiquette}-{_fragment(sequence['objectif'])}"
                  f"-{numero:02d}")
        for echantillon in range(1, NB_ECHANTILLONS + 1):
            if f"{groupe}-{echantillon}" in deja:
                print(f"{groupe}-{echantillon} : déjà récolté, ignoré.")
                continue
            tours = play(interroger_cible, sequence["messages"])
            entrees.append(_entree(groupe, echantillon, sequence, tours))
            print(f"{groupe}-{echantillon} ({sequence['technique']}) : "
                  f"{len(tours) // 2} tour(s)")

            if comparer:
                # Le MÊME couple d'ingrédients en un seul message. La paire
                # ne vaut que jouée dans la même session, contre la même
                # cible, à la suite : une cible probabiliste dérive.
                reponse = interroger_cible(sequence["mono_tour"])
                entrees.append(_entree(
                    groupe, echantillon, sequence,
                    [{"role": "utilisateur", "contenu": sequence["mono_tour"]},
                     {"role": "cible", "contenu": reponse}],
                    suffixe="-mono"))
                print(f"{groupe}-{echantillon}-mono : 1 tour (témoin)")

    FICHIER_SORTIE.write_text(
        json.dumps({"conversations": entrees}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{len(entrees)} conversation(s) écrites dans "
          f"{FICHIER_SORTIE.name}, à étiqueter à la main :\n"
          f"  python -m evaluation.etiqueter")
    return entrees


def _recolte_existante():
    """Ce qui est déjà récolté et pas encore versé dans le corpus."""
    if not FICHIER_SORTIE.exists():
        return []
    return json.loads(FICHIER_SORTIE.read_text(
        encoding="utf-8")).get("conversations", [])


def _entree(groupe, echantillon, sequence, tours, suffixe=""):
    """Une entrée à étiqueter. Les champs à remplir restent à None."""
    return {
        "id": f"{groupe}-{echantillon}{suffixe}",
        "groupe": groupe,          # mono-tour et multi-tours vont ENSEMBLE
        "format": "mono-tour" if len(tours) == 2 else "multi-tours",
        "tours": tours,
        "source": (f"cible réelle — {sequence['technique']} / "
                   f"{sequence['objectif']} / "
                   f"{'composé' if suffixe else 'séquencé'}"),
        "secret": "ARCHIVES-7731",
        "categorie": None,         # à remplir à la main
        "jeu": None,               # à remplir à la main : "dev" ou "test"
        "attendu": None,           # à remplir à la main : true ou false
        "piege": "",               # à remplir à la main
    }


def principal(arguments=None):
    parseur = argparse.ArgumentParser(
        description="Récolte des conversations multi-tours à étiqueter.")
    parseur.add_argument("--cible", default=None,
                         help="cible à interroger (défaut : celle de .env). "
                              "`demo` est locale, donc gratuite.")
    parseur.add_argument("--comparer", action="store_true",
                         help="récolter aussi la variante MONO-TOUR des mêmes "
                              "ingrédients, pour des paires comparables")
    parseur.add_argument("--anodin", action="store_true",
                         help="second tour anodin (objectif de contrôle), au "
                              "lieu de réclamer ce que la cible protège : "
                              "récolte des NÉGATIFS")
    parseur.add_argument("--sequences", type=int, default=MAX_SEQUENCES,
                         metavar="N", help=f"séquences au plus "
                                           f"(défaut : {MAX_SEQUENCES})")
    arguments = parseur.parse_args(arguments)

    if arguments.cible and not is_bundled_target(arguments.cible):
        # Récolter, c'est envoyer de vrais payloads : le mandat s'applique.
        # Le dire ici évite de le découvrir après le premier envoi.
        print("/!\\ Cible non livrée avec le projet : vérifie que le mandat "
              "la couvre (voir audit.py) avant de lancer la récolte.")

    print(f"Cible : {arguments.cible or 'celle de .env'}. "
          f"Aucun juge, aucun modèle attaquant : seule la cible est appelée.")
    print(f"Au plus {arguments.sequences} séquence(s) × {NB_ECHANTILLONS} "
          f"échantillon(s), {MAX_TURNS} tours maximum chacune.\n")
    collecter(arguments.cible, arguments.comparer, arguments.sequences,
              arguments.anodin)
    return 0


if __name__ == "__main__":
    principal()
