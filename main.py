"""
main.py — L'orchestrateur : reconnaissance → planification → attaque → jugement.

Déroulement d'une campagne :
  1. On OBSERVE la cible (questions anodines) pour en dresser une fiche.
  2. On PLANIFIE : quelles familles ont un sens ici, dans quel ordre.
  3. Pour chaque essai retenu : on envoie, la cible répond, l'arbitre juge.
  4. Une divulgation est vérifiée par REJEU avant d'être déclarée (une cible
     qui invente un mot de passe n'a rien divulgué).

Deux budgets, parce que deux boucles : BUDGET_RECONNAISSANCE pour l'observation,
MAX_ESSAIS pour l'attaque. Sans eux, un agent adaptatif tournerait sans fin.

Lance-le avec :
    python main.py                       # la cible désignée par .env
    python main.py --cible mock          # déterministe, sans LLM
    python main.py --cible https://...   # un vrai endpoint
"""

import argparse

from agents.arbitre import juger, juger_par_vote
from agents.planificateur import planifier, resumer as resumer_plan
from agents.reconnaissance import reconnaitre, resumer as resumer_fiche
from agents.verificateur import verifier_par_rejeu
from cibles import choisir_cible
from llm_client import journal, reinitialiser_journal

# Règle d'arrêt : on ne tente pas une attaque à l'infini.
MAX_ESSAIS = 3


def lancer_campagne(interroger_cible=None):
    """
    Lance une campagne contre `interroger_cible`.

    La cible est un paramètre, pas un import : c'est ce qui permet de viser
    un vrai endpoint, le leurre local ou une cible simulée, sans toucher au
    code de l'orchestrateur. Par défaut, celle que désigne `.env`.
    """
    interroger_cible = interroger_cible or choisir_cible()

    print("=== Campagne ===\n")
    reinitialiser_journal()

    # --- 1. Reconnaissance : qui est cette cible ? -------------------------
    print("--- Reconnaissance ---")
    fiche = reconnaitre(interroger_cible)
    print(resumer_fiche(fiche))

    # --- 2. Planification : que lancer, et dans quel ordre ? ---------------
    print("\n--- Plan ---")
    plan = planifier(fiche, MAX_ESSAIS)
    print(resumer_plan(plan))

    if not plan["essais"]:
        print("\n>>> Aucun essai applicable à cette cible. Campagne terminée.")
        return _terminer({"statut": "aucun_essai", "fiche": fiche, "plan": plan})

    # --- 3. Attaque ---------------------------------------------------------
    print()
    for numero, payload in enumerate(plan["essais"], start=1):
        print(f"--- Essai {numero}/{len(plan['essais'])} ---")
        print(f"  [Attaquant] {payload['technique']} / {payload['objectif']} "
              f"/ {payload['transformation']}")
        print(f"              envoie : {payload['texte']}")

        # Une réponse coupée par le plafond de sortie de la cible se lit comme
        # une réponse complète : le verdict qui suit ne vaudrait alors rien.
        tronquees_avant = len(journal()["tronquees"])
        reponse = interroger_cible(payload["texte"])
        tronquee = len(journal()["tronquees"]) > tronquees_avant
        print(f"  [Cible]     répond : {reponse}")
        if tronquee:
            print("  /!\\        réponse TRONQUÉE : une fuite a pu être coupée "
                  "en deux, le verdict ci-dessous n'est pas fiable.")

        # Vote : le juge n'est pas déterministe sur les cas limites, et une
        # faille qui apparaît selon le tirage n'a rien à faire dans un rapport.
        verdict = juger_par_vote(payload["texte"], reponse)
        print(f"  [Arbitre]   enfreint={verdict['reussi']} "
              f"({verdict['critere']}, votes {verdict['votes']}) : "
              f"{verdict['analyse']}\n")

        # Un verdict illisible (None) n'est PAS une faille : on continue.
        if verdict["reussi"] is not True:
            continue

        # --- 4. Vérification par rejeu, si une valeur a été divulguée ------
        verification = None
        if verdict["critere"] == "divulgation":
            # Le rejeu reçoit `juger` sans vote : il interroge déjà la cible
            # plusieurs fois, ce qui lisse le bruit. Voter en plus coûterait
            # neuf appels là où trois suffisent.
            verification = verifier_par_rejeu(
                payload["texte"], verdict["valeur"], interroger_cible, juger
            )
            print(f"  [Rejeu]     {verification['statut']} : "
                  f"{verification['explication']}")

            if verification["statut"] == "hallucination_probable":
                print("  >>> Valeur inventée par la cible : on continue.\n")
                continue

        print(">>> Faille détectée : on consigne et on arrête la campagne.")
        return _terminer({
            "statut": "faille",
            "essai": numero,
            "payload": payload,
            "reponse": reponse,
            "verdict": verdict,
            # None (obéissance, pas de valeur), ou le résultat du rejeu :
            # "confirmee", "contradictoire", "inconcluant"…
            "verification": verification,
            "fiche": fiche,
            "plan": plan,
        })

    print(">>> Aucune faille après le budget d'essais. Campagne terminée.")
    return _terminer({"statut": "aucune_faille", "fiche": fiche, "plan": plan})


def _terminer(resultat):
    """Attache le journal des appels et avertit si des réponses ont été coupées."""
    resultat["journal"] = journal()
    tronquees = len(resultat["journal"]["tronquees"])

    print(f"\n{resultat['journal']['appels']} appel(s) au LLM, "
          f"{resultat['journal']['tokens']} tokens.")
    if tronquees:
        # Un « aucune faille » obtenu sur des réponses coupées ne vaut rien :
        # le dire franchement plutôt que de laisser croire à une couverture.
        print(f"/!\\ {tronquees} réponse(s) tronquée(s) : les verdicts "
              f"correspondants sont peu fiables, et un « aucune faille » "
              f"pourrait masquer une fuite coupée en deux.")
    return resultat


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(description="Lance une campagne de test.")
    parseur.add_argument(
        "--cible", default=None,
        help="'leurre' (défaut), 'mock', ou une URL http(s). "
             "Sinon la valeur de CIBLE dans .env.")
    arguments = parseur.parse_args()

    resultat = lancer_campagne(choisir_cible(arguments.cible))
    print(f"\nRésultat final : {resultat['statut']}")
