"""
evaluation/mesurer_adaptation_reelle.py — L'adaptation gagne-t-elle contre une
VRAIE cible ?

`mesurer_adaptation.py` répond déjà à cette question, mais sur des cibles
SIMULÉES dont on décrète quelles techniques cèdent. Ici la cible est un vrai
LLM mal protégé (`--cible demo`), avec de vrais payloads et de vraies réponses
probabilistes.

POURQUOI UN JUGE LOCAL. Mesuré le 2026-11-12 : une campagne coûte ~13 000
tokens par essai avec le juge Groq, soit ~520 000 tokens pour une seule paire
à budget 20 — 2,6 jours de quota gratuit. Et une paire ne conclurait rien, la
cible étant probabiliste : il en faudrait cinq à dix, donc des semaines. Avec
un juge local la mesure est gratuite, donc répétable autant qu'il faut.

LE BIAIS, ET CE QU'IL FAUT EN LIRE. llama3.2 comme juge plafonne à 50 % de
rappel : il rate une faille sur deux. Ce biais n'est PAS symétrique entre les
deux bras, et c'est le point — l'adaptation se nourrit des VERDICTS
(`technique_efficace` remonte ce qui vient de marcher), alors que le bras
statique suit son plan sans rien écouter.

**Correction apportée après les 40 paires du 2026-11-12 :** cette note disait
qu'un juge médiocre PRIVE l'adaptation de signal, donc que la mesure
sous-estime son gain. C'est incomplet, et l'erreur compte. Un juge qui rate
une faille ne reste pas muet : il rend un verdict NÉGATIF, que l'adaptation
lit comme `technique_bloquee` et qui l'éloigne d'une technique qui marchait.
Il ne l'affame pas, il la DÉSINFORME. Le biais peut donc rendre l'adaptatif
activement moins bon que le témoin, et pas seulement moins bon qu'il ne l'est.

Conséquence pour lire un résultat :
- si l'adaptatif gagne malgré ce handicap, c'est une BORNE BASSE du gain réel,
  et le résultat est solide ;
- s'il perd ou fait match nul, on ne peut RIEN conclure sur l'adaptation —
  seulement que l'ensemble {adaptation + ce juge} ne vaut pas le plan statique.
  Ce qui est utile à savoir, mais ne répond pas à la question posée.

Lance-le depuis la racine du projet, avec PROFIL_ARBITRE=local :
    python -m evaluation.mesurer_adaptation_reelle --paires 3 --budget 8
"""

import argparse
import contextlib
import io
import json
import os
import tempfile
import time
from pathlib import Path

# Les deux bras doivent voir exactement la même cible et le même vivier : seul
# `adaptatif` change. Tout le reste est tenu constant par construction.
CIBLE = "demo"


def _campagne(adaptatif, budget):
    """Une campagne complète, sans bruit sur la sortie standard."""
    import main
    from cibles import choisir_cible

    budget_initial = main.MAX_ESSAIS
    main.MAX_ESSAIS = budget
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return main.lancer_campagne(choisir_cible(CIBLE), CIBLE,
                                        adaptatif=adaptatif)
    finally:
        main.MAX_ESSAIS = budget_initial


def _mesures(resultat):
    """Ce qu'on retient d'une campagne : trouvailles ET couverture."""
    import statistiques

    etats = resultat.get("etats") or []
    taux = statistiques.taux_de_succes(etats)
    return {
        "constats": len(resultat.get("constats") or []),
        "essais": len(resultat.get("lances") or []),
        "scorables": taux["scorables"],
        "non_scorables": taux["non_scorables"],
        # La couverture compte autant que les trouvailles : un bras qui trouve
        # plus en ne touchant qu'une famille n'est pas forcément meilleur.
        "modules": len({e.get("groupe") or e["technique"]
                        for e in resultat.get("lances") or []}),
        "familles": len({e["famille_owasp"] for e in
                         resultat.get("lances") or [] if e["famille_owasp"]}),
    }


def une_paire(budget, afficher=print):
    """Les deux bras, dans la foulée, sur la même cible."""
    paire = {}
    for bras, adaptatif in (("adaptatif", True), ("statique", False)):
        depart = time.monotonic()
        resultat = _campagne(adaptatif, budget)
        paire[bras] = {**_mesures(resultat),
                       "secondes": round(time.monotonic() - depart, 1)}
        m = paire[bras]
        afficher(f"    {bras:10s} {m['constats']} constat(s), "
                 f"{m['modules']} module(s), "
                 f"{m['non_scorables']} non scorable(s), {m['secondes']} s")
    return paire


def principal(arguments=None):
    parseur = argparse.ArgumentParser(
        description="Adaptatif contre plan statique, sur la cible de "
                    "démonstration réelle.")
    parseur.add_argument("--paires", type=int, default=3,
                         help="nombre de paires à lancer (défaut : 3)")
    parseur.add_argument("--budget", type=int, default=8,
                         help="essais par campagne (défaut : 8)")
    parseur.add_argument("--sortie", default=None, metavar="FICHIER",
                         help="où écrire les résultats au fil de l'eau")
    arguments = parseur.parse_args(arguments)

    from config import PROFIL_ARBITRE
    print(f"Juge : {PROFIL_ARBITRE}. Cible : {CIBLE}. "
          f"{arguments.paires} paire(s) × {arguments.budget} essais.")
    if PROFIL_ARBITRE != "local":
        print("/!\\ Juge NON local : cette mesure va consommer du quota. "
              "Lance-la avec PROFIL_ARBITRE=local.")
    print()

    sortie = Path(arguments.sortie) if arguments.sortie else None
    paires = []
    # Boucle bornée, comme partout : le nombre de paires est un argument, pas
    # une condition d'arrêt découverte en route.
    for numero in range(1, arguments.paires + 1):
        print(f"  paire {numero}/{arguments.paires}")
        paires.append(une_paire(arguments.budget))
        if sortie:
            # Écrit à chaque paire : une mesure interrompue garde ce qu'elle
            # a déjà établi, comme la piste d'audit d'une campagne.
            sortie.write_text(json.dumps(paires, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    _bilan(paires, arguments.budget)
    return paires


def _bilan(paires, budget):
    if not paires:
        return
    print(f"\n=== Bilan sur {len(paires)} paire(s), budget {budget} ===\n")
    print(f"{'':12s} {'constats':>10s} {'modules':>9s} {'non scor.':>10s}")
    for bras in ("adaptatif", "statique"):
        moyenne = {cle: sum(p[bras][cle] for p in paires) / len(paires)
                   for cle in ("constats", "modules", "non_scorables")}
        print(f"  {bras:10s} {moyenne['constats']:>10.2f} "
              f"{moyenne['modules']:>9.2f} {moyenne['non_scorables']:>10.2f}")

    ecarts = [p["adaptatif"]["constats"] - p["statique"]["constats"]
              for p in paires]
    gagne = sum(1 for e in ecarts if e > 0)
    perd = sum(1 for e in ecarts if e < 0)
    print(f"\n  écart par paire : {ecarts}")
    print(f"  l'adaptatif fait mieux {gagne}×, moins bien {perd}×, "
          f"à égalité {len(ecarts) - gagne - perd}×")

    # Le rappel du biais, à l'endroit où on lit le résultat : sans lui, un
    # écart nul se lirait comme « l'adaptation n'apporte rien ».
    print("\n  Rappel : le juge local rate une faille sur deux, et l'adaptation")
    print("  se nourrit des verdicts. Un gain observé ici est une BORNE BASSE ;")
    print("  une absence de gain ne permet aucune conclusion.")


if __name__ == "__main__":
    principal()
