"""
evaluation/evaluer_arbitre.py — Mesure la fiabilité de l'arbitre (Phase 2).

Principe : on soumet à l'arbitre des échanges dont on connaît DÉJÀ la bonne
réponse (étiquetés à la main dans echanges_etiquetes.json), puis on compte
ses erreurs. Sans ça, impossible de savoir si une "faille détectée" par la
campagne en est vraiment une.

Les deux erreurs n'ont pas le même coût :
- Faux positif (FP) : le juge crie à la faille alors qu'il n'y en a pas.
  Le rapport final serait pollué de fausses alertes.
- Faux négatif (FN) : le juge rate une vraie faille. Plus grave pour un
  outil de sécurité : la campagne conclut "aucune faille" à tort.

Lance-le depuis la racine du projet avec :  python -m evaluation.evaluer_arbitre
"""

import json
from pathlib import Path

from agents.arbitre import juger

FICHIER_ECHANGES = Path(__file__).parent / "echanges_etiquetes.json"


def charger_echanges():
    with open(FICHIER_ECHANGES, encoding="utf-8") as f:
        return json.load(f)["echanges"]


def ratio(numerateur, denominateur):
    """Évite la division par zéro quand une catégorie est vide."""
    return numerateur / denominateur if denominateur else 0.0


def evaluer():
    echanges = charger_echanges()
    compteurs = {"VP": 0, "FP": 0, "VN": 0, "FN": 0, "a_revoir": 0}
    erreurs = []

    # Boucle bornée par nature : un appel au juge par échange étiqueté.
    for echange in echanges:
        resultat = juger(echange["payload"], echange["reponse"])
        attendu = echange["attendu"]
        obtenu = resultat["reussi"]

        if obtenu is None:
            case = "a_revoir"
        elif obtenu and attendu:
            case = "VP"
        elif obtenu and not attendu:
            case = "FP"
        elif not obtenu and not attendu:
            case = "VN"
        else:
            case = "FN"
        compteurs[case] += 1

        symbole = "ok " if case in ("VP", "VN") else "ERR"
        print(f"[{symbole}] {echange['id']} {case:<8} "
              f"attendu={attendu!s:<5} obtenu={obtenu!s:<5} "
              f"critère={resultat['critere']}")

        if case not in ("VP", "VN"):
            erreurs.append((echange, resultat))

    vp, fp = compteurs["VP"], compteurs["FP"]
    total = len(echanges)
    vraies_failles = sum(1 for e in echanges if e["attendu"])

    print("\n=== Bilan ===")
    print(f"Échanges évalués : {total}")
    print(f"VP={vp}  FP={fp}  VN={compteurs['VN']}  FN={compteurs['FN']}  "
          f"à revoir={compteurs['a_revoir']}")
    # Précision : quand le juge dit "faille", a-t-il raison ?
    print(f"Précision : {ratio(vp, vp + fp):.0%}")
    # Rappel STRICT : parmi toutes les vraies failles, combien sont confirmées ?
    # Une abstention sur une vraie faille compte comme ratée : on ne veut pas
    # qu'un juge améliore son score en s'abstenant dès que c'est difficile.
    print(f"Rappel    : {ratio(vp, vraies_failles):.0%}")
    print(f"Exactitude: {ratio(vp + compteurs['VN'], total):.0%}")
    print(f"À revoir  : {ratio(compteurs['a_revoir'], total):.0%}")

    if erreurs:
        print("\n=== Détail des erreurs ===")
        for echange, resultat in erreurs:
            print(f"\n{echange['id']} — {echange['piege']}")
            print(f"  Juge : {resultat['analyse']}")

    return compteurs


if __name__ == "__main__":
    evaluer()
