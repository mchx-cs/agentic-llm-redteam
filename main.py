"""
main.py — L'orchestrateur : la boucle complète attaquant → cible → arbitre.

C'est le squelette du schéma 2 : on génère une tentative, on l'envoie à la
cible, l'arbitre juge, et si c'est un échec on recommence — dans la limite
d'un BUDGET d'essais (le garde-fou anti-boucle-infinie / anti-facture).

Lance-le avec :  python main.py
"""

from agents.attaquant import generer_payload
from agents.arbitre import juger
from cible import interroger_cible

# Règle d'arrêt : on ne tente pas une attaque à l'infini.
MAX_ESSAIS = 3


def lancer_campagne():
    print("=== Campagne de test (payloads de contrôle) ===\n")

    reponse = None  # réponse du tour précédent (servira à l'adaptation plus tard)

    for essai in range(1, MAX_ESSAIS + 1):
        print(f"--- Essai {essai}/{MAX_ESSAIS} ---")

        # 1. L'attaquant produit une tentative (texte + sa provenance).
        payload = generer_payload(essai, reponse_precedente=reponse)
        print(f"  [Attaquant] {payload['technique']} / {payload['objectif']} "
              f"/ {payload['transformation']}")
        print(f"              envoie : {payload['texte']}")

        # 2. La cible répond.
        reponse = interroger_cible(payload["texte"])
        print(f"  [Cible]     répond : {reponse}")

        # 3. L'arbitre juge.
        verdict = juger(payload["texte"], reponse)
        print(f"  [Arbitre]   enfreint={verdict['reussi']} "
              f"({verdict['critere']}) : {verdict['justification']}\n")

        # 4. Faille trouvée ? On consigne et on s'arrête.
        #    Un verdict illisible (None) n'est PAS une faille : on continue.
        if verdict["reussi"] is True:
            print(">>> Faille détectée : on consigne et on arrête la campagne.")
            return {
                "statut": "faille",
                "essai": essai,
                "payload": payload,
                "reponse": reponse,
                "verdict": verdict,
            }

    print(">>> Aucune faille après le budget d'essais. Campagne terminée.")
    return {"statut": "aucune_faille"}


if __name__ == "__main__":
    resultat = lancer_campagne()
    print("\nRésultat final :", resultat)
