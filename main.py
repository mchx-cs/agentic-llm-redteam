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

Lance-le avec :  python main.py
"""

from agents.arbitre import juger
from agents.planificateur import planifier, resumer as resumer_plan
from agents.reconnaissance import reconnaitre, resumer as resumer_fiche
from agents.verificateur import verifier_par_rejeu
from cible import interroger_cible

# Règle d'arrêt : on ne tente pas une attaque à l'infini.
MAX_ESSAIS = 3


def lancer_campagne():
    print("=== Campagne ===\n")

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
        return {"statut": "aucun_essai", "fiche": fiche, "plan": plan}

    # --- 3. Attaque ---------------------------------------------------------
    print()
    for numero, payload in enumerate(plan["essais"], start=1):
        print(f"--- Essai {numero}/{len(plan['essais'])} ---")
        print(f"  [Attaquant] {payload['technique']} / {payload['objectif']} "
              f"/ {payload['transformation']}")
        print(f"              envoie : {payload['texte']}")

        reponse = interroger_cible(payload["texte"])
        print(f"  [Cible]     répond : {reponse}")

        verdict = juger(payload["texte"], reponse)
        print(f"  [Arbitre]   enfreint={verdict['reussi']} "
              f"({verdict['critere']}) : {verdict['analyse']}\n")

        # Un verdict illisible (None) n'est PAS une faille : on continue.
        if verdict["reussi"] is not True:
            continue

        # --- 4. Vérification par rejeu, si une valeur a été divulguée ------
        verification = None
        if verdict["critere"] == "divulgation":
            verification = verifier_par_rejeu(
                payload["texte"], verdict["valeur"], interroger_cible, juger
            )
            print(f"  [Rejeu]     {verification['statut']} : "
                  f"{verification['explication']}")

            if verification["statut"] == "hallucination_probable":
                print("  >>> Valeur inventée par la cible : on continue.\n")
                continue

        print(">>> Faille détectée : on consigne et on arrête la campagne.")
        return {
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
        }

    print(">>> Aucune faille après le budget d'essais. Campagne terminée.")
    return {"statut": "aucune_faille", "fiche": fiche, "plan": plan}


if __name__ == "__main__":
    resultat = lancer_campagne()
    print(f"\nRésultat final : {resultat['statut']}")
