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

Deux jeux, pour ne pas se mentir (surapprentissage) :
- "dev"  : on règle l'arbitre en regardant ces résultats. À force, ils ne
           mesurent plus le juge, mais notre talent à corriger ces cas précis.
- "test" : jeu GELÉ. On ne le consulte qu'aux moments clés, et on ne règle
           JAMAIS l'arbitre d'après lui. Chaque consultation est journalisée
           dans journal_test.jsonl : la discipline devient vérifiable.

Lance-le depuis la racine du projet avec :
    python -m evaluation.evaluer_arbitre            # jeu de développement
    python -m evaluation.evaluer_arbitre --test     # jeu de test gelé
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from agents.arbitre import juger

FICHIER_ECHANGES = Path(__file__).parent / "echanges_etiquetes.json"
JOURNAL_TEST = Path(__file__).parent / "journal_test.jsonl"


def charger_echanges(jeu):
    """Charge les échanges d'un jeu ("dev" ou "test"), après contrôle."""
    with open(FICHIER_ECHANGES, encoding="utf-8") as f:
        echanges = json.load(f)["echanges"]

    # Garde-fou : un même scénario (groupe) ne doit JAMAIS être réparti entre
    # les deux jeux. Sinon le test contiendrait une simple reformulation d'un
    # cas de dev, déjà "vu" pendant le réglage : il ne mesurerait plus rien.
    jeu_du_groupe = {}
    for echange in echanges:
        groupe = echange["groupe"]
        jeu_du_groupe.setdefault(groupe, echange["jeu"])
        if jeu_du_groupe[groupe] != echange["jeu"]:
            raise ValueError(
                f"Le groupe {groupe} est réparti entre 'dev' et 'test' "
                f"({echange['id']}) : fuite entre les deux jeux."
            )

    return [e for e in echanges if e["jeu"] == jeu]


def ratio(numerateur, denominateur):
    """Évite la division par zéro quand une catégorie est vide."""
    return numerateur / denominateur if denominateur else 0.0


def journaliser_consultation_test(compteurs, metriques):
    """Ajoute une ligne au journal des consultations du jeu de test."""
    entree = {
        "date": datetime.now().isoformat(timespec="seconds"),
        **compteurs,
        **{nom: round(valeur, 3) for nom, valeur in metriques.items()},
    }
    with open(JOURNAL_TEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")


def evaluer(jeu="dev"):
    echanges = charger_echanges(jeu)
    compteurs = {"VP": 0, "FP": 0, "VN": 0, "FN": 0, "a_revoir": 0}
    erreurs = []

    if jeu == "test":
        print("!!! Jeu de TEST gelé : ne règle pas l'arbitre d'après ces "
              "résultats. Cette consultation est journalisée.\n")

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
        print(f"[{symbole}] {echange['id']:<6} {case:<8} "
              f"attendu={attendu!s:<5} obtenu={obtenu!s:<5} "
              f"{echange['categorie']}")

        if case not in ("VP", "VN"):
            erreurs.append((echange, resultat))

    vp, fp = compteurs["VP"], compteurs["FP"]
    total = len(echanges)
    vraies_failles = sum(1 for e in echanges if e["attendu"])
    metriques = {
        # Précision : quand le juge dit "faille", a-t-il raison ?
        "precision": ratio(vp, vp + fp),
        # Rappel STRICT : parmi toutes les vraies failles, combien sont
        # confirmées ? Une abstention sur une vraie faille compte comme ratée :
        # un juge ne doit pas gonfler son score en s'abstenant quand c'est dur.
        "rappel": ratio(vp, vraies_failles),
        "exactitude": ratio(vp + compteurs["VN"], total),
        "a_revoir_taux": ratio(compteurs["a_revoir"], total),
    }

    print(f"\n=== Bilan (jeu {jeu}) ===")
    print(f"Échanges évalués : {total}")
    print(f"VP={vp}  FP={fp}  VN={compteurs['VN']}  FN={compteurs['FN']}  "
          f"à revoir={compteurs['a_revoir']}")
    print(f"Précision : {metriques['precision']:.0%}")
    print(f"Rappel    : {metriques['rappel']:.0%}")
    print(f"Exactitude: {metriques['exactitude']:.0%}")
    print(f"À revoir  : {metriques['a_revoir_taux']:.0%}")

    if erreurs:
        print("\n=== Détail des erreurs ===")
        for echange, resultat in erreurs:
            print(f"\n{echange['id']} [{echange['categorie']}] — {echange['piege']}")
            print(f"  Juge : {resultat['analyse']}")

    if jeu == "test":
        journaliser_consultation_test(compteurs, metriques)

    return compteurs, metriques


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description="Mesure la fiabilité de l'arbitre.")
    parseur.add_argument("--test", action="store_true",
                         help="évaluer sur le jeu de test gelé (consultation journalisée)")
    arguments = parseur.parse_args()
    evaluer("test" if arguments.test else "dev")
