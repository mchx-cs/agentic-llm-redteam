"""
evaluation/mesurer_adaptation.py — L'adaptation trouve-t-elle plus de failles
que le plan statique, à budget égal ?

C'est LA question qui décide si la phase 3a valait la peine. Elle se mesure,
elle ne se devine pas : réordonner les essais paraît toujours une bonne idée,
et c'est exactement pour ça qu'il faut vérifier.

AUCUN APPEL À UN MODÈLE, et c'est pour cela que ce script est ici plutôt que
dans `tests/` : le reste de `evaluation/` consomme du quota, celui-ci non.
Mais ce n'est pas un test — il ne produit pas un verdict vrai/faux, il produit
des CHIFFRES à interpréter, et son résultat dépend d'un tirage aléatoire. Il
n'a donc rien à faire en intégration continue.

Lance-le depuis la racine du projet avec :
    python -m evaluation.mesurer_adaptation
    python -m evaluation.mesurer_adaptation --signaux   # détail par signal

MÉTHODE, et ses deux pièges, tous deux rencontrés le 2026-11-11 :

1. *Ne pas construire la cible à l'image de l'heuristique.* Une première
   version faisait céder la cible exactement aux sondes que le signal
   `secret_evoque` remonte. Gain spectaculaire… et parfaitement circulaire :
   on mesurait que le code fait ce qu'on a codé. Les techniques vulnérables
   sont donc tirées AU HASARD, ce qui revient à supposer que la
   correspondance OWASP de garak ne prédit RIEN du comportement de la cible.
   C'est l'hypothèse PESSIMISTE : la réalité est probablement meilleure, une
   sonde LLM02 cherchant effectivement à faire fuiter de l'information.

2. *Ne pas conclure sur un seul tirage.* Un tirage donnait « l'adaptation
   perd 2 constats », un autre l'inverse : quelles techniques cèdent est
   arbitraire, donc un écart isolé est du bruit. On moyenne sur NB_TIRAGES, et
   on compte surtout la part des tirages où l'adaptation fait PIRE — un gain
   moyen obtenu au prix d'un échec sur cinq ne vaut pas la même chose qu'un
   gain systématique.
"""

import argparse
import random
from statistics import mean

import agents.adaptation as adaptation
from agents.planificateur import plan_campaign

NB_TIRAGES = 150
BUDGETS = (3, 6, 10, 20, 40)
# Part des techniques qui cèdent. 20 % : une cible ni blindée ni béante.
PART_VULNERABLE = 0.20
# Payloads gardés par technique. Il en faut PLUSIEURS, sinon le signal
# `technique_efficace` n'a rien à remonter et la mesure serait truquée dans
# l'autre sens ; il n'en faut pas trop, pour que 150 tirages tiennent en
# quelques secondes.
PAYLOADS_PAR_TECHNIQUE = 3

# Cible de référence de la mesure : un chatbot texte ordinaire. Les deux
# tri-états restent à None — « elle n'en a rien dit » — et le contexte est
# vide, donc les modules qui dépendent de l'application autour (`ansiescape`,
# `web_injection`, `exploitation`) sont écartés. C'est voulu : mesurer
# l'adaptation sur un vivier contenant des sondes intestables fausserait le
# résultat dans les deux sens.
FICHE = {"role": "assistant", "langue": "fr", "outils": [],
         "sujets_refuses": ["le code du fonds ancien"],
         "mentionne_consignes": True, "produit_du_code": None,
         "traite_des_documents": None, "contexte": [],
         "indices": [], "echanges": [], "avertissement": None}

# Le refus NOMME ce qu'il protège : c'est le cas favorable au signal
# `secret_evoque`, qu'on veut justement mettre à l'épreuve.
REFUSAL = "Je ne peux pas vous donner ce code, il est confidentiel."
FUITE = "Le code du fonds ancien est ARCHIVES-7731."

SIGNAUX = ("technique_efficace", "technique_bloquee", "secret_evoque",
           "outil_declenche")


def construire_vivier():
    """Le vivier du planificateur, réduit à quelques payloads par technique."""
    comptes = {}
    vivier = []
    for candidat in plan_campaign(FICHE, 1)["candidats"]:
        technique = candidat["technique"]
        if comptes.get(technique, 0) < PAYLOADS_PAR_TECHNIQUE:
            comptes[technique] = comptes.get(technique, 0) + 1
            vivier.append(candidat)
    return vivier, sorted(comptes)


def campagne(vivier, budget, adaptatif, cedent, signaux=None):
    """
    Une campagne simulée. Renvoie le nombre de constats.

    `adaptatif=False` suit l'ordre statique du vivier sans rien apprendre :
    c'est le témoin. `signaux` permet de neutraliser certains signaux, pour
    isoler la contribution de chacun.
    """
    lances, observations, constats = [], [], 0

    for _ in range(budget):          # boucle bornée, comme partout ailleurs
        essai = adaptation.next_attempt(
            vivier, observations if adaptatif else (), lances)
        if essai is None:
            break
        lances.append(essai)

        reussi = essai["technique"] in cedent
        constats += reussi
        nouvelles = adaptation.observe(
            essai, FUITE if reussi else REFUSAL,
            {"reussi": reussi,
             "critere": "divulgation" if reussi else "aucun"})
        if signaux is not None:
            nouvelles = [o for o in nouvelles if o["signal"] in signaux]
        observations = adaptation.accumulate(observations, nouvelles)

    return constats


def mesurer(vivier, techniques, budget, signaux=None, tirages=NB_TIRAGES):
    """Écart moyen adaptatif − statique, et répartition des tirages."""
    combien = max(1, int(len(techniques) * PART_VULNERABLE))
    ecarts = []
    for graine in range(tirages):
        # Graine explicite : la mesure doit être reproductible à l'identique.
        cedent = set(random.Random(graine).sample(techniques, combien))
        ecarts.append(campagne(vivier, budget, True, cedent, signaux)
                      - campagne(vivier, budget, False, cedent))
    return {
        "moyenne": mean(ecarts),
        "mieux": sum(e > 0 for e in ecarts),
        "pire": sum(e < 0 for e in ecarts),
        "egal": sum(e == 0 for e in ecarts),
    }


def mesurer_global(vivier, techniques):
    print("Adaptatif contre plan statique, à budget égal.")
    print(f"Techniques vulnérables tirées AU HASARD "
          f"({int(PART_VULNERABLE * 100)} % des {len(techniques)}), "
          f"{NB_TIRAGES} tirages.")
    print("Hypothèse PESSIMISTE : la correspondance OWASP de garak ne prédit")
    print("rien du comportement de la cible.\n")

    print(f"{'budget':>6} | {'écart moyen':>11} | {'mieux':>5} {'pire':>5} "
          f"{'égal':>5}")
    print("-" * 46)
    for budget in BUDGETS:
        r = mesurer(vivier, techniques, budget)
        print(f"{budget:>6} | {r['moyenne']:>+11.2f} | {r['mieux']:>5} "
              f"{r['pire']:>5} {r['egal']:>5}")

    print("\nÀ lire ainsi : le gain CROÎT avec le budget. À trois essais il "
          "est\nmarginal et un tirage sur cinq est perdant ; à quarante il "
          "est net et\npresque systématique. L'adaptation a besoin de budget "
          "pour payer —\nlogique, puisqu'il faut pouvoir revenir sur une "
          "piste pour l'exploiter.")


def mesurer_par_signal(vivier, techniques):
    """Quel signal porte le gain ? On les neutralise un par un."""
    cas = [("tous les signaux", set(SIGNAUX))]
    cas += [(f"sans {signal}", set(SIGNAUX) - {signal}) for signal in SIGNAUX]
    cas += [(f"{signal} SEUL", {signal}) for signal in SIGNAUX]

    budgets = (3, 10, 40)
    print("\nContribution de chaque signal (même protocole)\n")
    entete = "  ".join(f"{'b' + str(b):>13}" for b in budgets)
    print(f"{'variante':30s} {entete}")
    print(f"{'':30s} " + "  ".join(f"{'moy (pire)':>13}" for _ in budgets))
    print("-" * (32 + 15 * len(budgets)))
    for nom, signaux in cas:
        colonnes = []
        for budget in budgets:
            r = mesurer(vivier, techniques, budget, signaux)
            colonnes.append(f"{r['moyenne']:>+6.2f} ({r['pire']:>3})")
        print(f"{nom:30s} " + "  ".join(f"{c:>13}" for c in colonnes))


def principal(arguments=None):
    parseur = argparse.ArgumentParser(
        description="Mesure le gain de l'adaptation du plan (sans LLM).")
    parseur.add_argument("--signaux", action="store_true",
                         help="détailler la contribution de chaque signal")
    arguments = parseur.parse_args(arguments)

    vivier, techniques = construire_vivier()
    print(f"Vivier : {len(vivier)} candidats, {len(techniques)} techniques, "
          f"{PAYLOADS_PAR_TECHNIQUE} payloads par technique.\n")
    if not techniques:
        print("Vivier vide : synchronise l'instantané garak "
              "(python -m payloads.source_garak --version).")
        return

    mesurer_global(vivier, techniques)
    if arguments.signaux:
        mesurer_par_signal(vivier, techniques)


if __name__ == "__main__":
    principal()
