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
import sys
from datetime import datetime
from pathlib import Path

from audit import (FICHIER_AUTORISATION, AutorisationManquante, PisteAudit,
                   exiger)
from agents.adaptation import cumuler, observer, prochain
from agents.arbitre import juger, juger_par_vote
from agents.planificateur import planifier, resumer as resumer_plan
from agents.reconnaissance import (CONTEXTES_CONNUS, reconnaitre,
                                    resumer as resumer_fiche)
from agents.verificateur import verifier_par_rejeu
from cibles import choisir_cible
from config import BUDGET_APPELS, BUDGET_TOKENS, CIBLE
from llm_client import BudgetDepasse, journal, reinitialiser_journal
from rapport import enregistrer

# Règle d'arrêt : on ne tente pas une attaque à l'infini.
MAX_ESSAIS = 3


def lancer_campagne(interroger_cible=None, nom_cible=None, piste=None,
                    contexte=()):
    """
    Lance une campagne contre `interroger_cible`.

    La cible est un paramètre, pas un import : c'est ce qui permet de viser
    un vrai endpoint, le leurre local ou une cible simulée, sans toucher au
    code de l'orchestrateur. Par défaut, celle que désigne `.env`.

    `piste` est une PisteAudit facultative. Quand elle est fournie, chaque
    échange avec la cible y est consigné au fil de l'eau — y compris ceux de
    la reconnaissance et du rejeu, puisque la cible y est tracée en amont.
    """
    interroger_cible = interroger_cible or choisir_cible()
    nom_cible = nom_cible or CIBLE

    print("=== Campagne ===\n")
    # Le budget est armé ICI, pas dans llm_client : les scripts d'évaluation
    # consomment bien plus qu'une campagne et n'ont aucune raison d'être
    # coupés au milieu d'une mesure.
    reinitialiser_journal(BUDGET_APPELS, BUDGET_TOKENS)

    # --- 1. Reconnaissance : qui est cette cible ? -------------------------
    print("--- Reconnaissance ---")
    try:
        fiche = reconnaitre(piste.tracer("reconnaissance", interroger_cible)
                            if piste else interroger_cible)
    except BudgetDepasse as arret:
        print(f"\n>>> {arret}")
        return _terminer({"statut": "budget_epuise", "fiche": None,
                          "plan": {"essais": [], "candidats": [],
                                   "ecartees": []},
                          "constats": [], "ecourtee": str(arret)})
    # Le contexte vient de l'OPÉRATEUR, pas d'une sonde : une cible ne sait
    # pas dans quoi sa sortie est rendue, et le lui demander inviterait à
    # l'hallucination. On le verse donc après coup, sans toucher aux faits
    # observés.
    fiche["contexte"] = list(contexte)
    print(resumer_fiche(fiche))

    # --- 2. Planification : que lancer, et dans quel ordre ? ---------------
    print("\n--- Plan ---")
    plan = planifier(fiche, MAX_ESSAIS)
    print(resumer_plan(plan))

    if not plan["essais"]:
        print("\n>>> Aucun essai applicable à cette cible. Campagne terminée.")
        return _terminer({"statut": "aucun_essai", "fiche": fiche, "plan": plan,
                          "constats": []})

    # --- 3. Attaque ---------------------------------------------------------
    # On va au BOUT du budget, au lieu de s'arrêter à la première faille : un
    # rapport n'a de valeur que s'il dit tout ce qui a été trouvé, et sur quoi
    # il s'est tu. S'arrêter tôt empêcherait toute affirmation de couverture.
    #
    # Le prochain essai n'est pas lu dans une liste figée : il est CHOISI à
    # chaque tour dans le vivier du planificateur, d'après ce que la cible a
    # déjà répondu (phase 3a, agents/adaptation.py). La boucle reste bornée
    # par MAX_ESSAIS — l'adaptation change l'ordre, jamais le nombre d'essais.
    constats = []
    observations = []       # ce qu'on a appris de la cible, cumulé
    lances = []             # les essais réellement envoyés, dans l'ordre
    ecourtee = None
    print()
    for numero in range(1, MAX_ESSAIS + 1):
        payload = prochain(plan["candidats"], observations, lances)
        if payload is None:
            print(">>> Vivier épuisé : plus aucun essai applicable.")
            break
        lances.append(payload)

        print(f"--- Essai {numero}/{MAX_ESSAIS} ---")
        print(f"  [Attaquant] {payload['technique']} / "
              f"{payload['objectif'] or 'payload complet'} "
              f"/ {payload['transformation']}")
        if payload.get("raisons_adaptation"):
            # Le solde d'abord : un essai peut cumuler bonus et malus, et sans
            # lui les raisons semblent se contredire.
            print(f"  [Adaptation] solde {payload['score_adaptation']:+d} "
                  f"sur sa priorité de départ "
                  f"({payload['priorite']}) :")
            for raison in payload["raisons_adaptation"]:
                print(f"               - {raison}")
        print(f"              envoie : {payload['texte']}")

        try:
            # Une réponse coupée par le plafond de sortie de la cible se lit
            # comme une réponse complète : le verdict ne vaudrait alors rien.
            tronquees_avant = len(journal()["tronquees"])
            reponse = interroger_cible(payload["texte"])
            tronquee = len(journal()["tronquees"]) > tronquees_avant
            if piste:
                piste.consigner_echange("attaque", payload["texte"], reponse,
                                        tronquee)
            print(f"  [Cible]     répond : {reponse}")
            if tronquee:
                print("  /!\\        réponse TRONQUÉE : une fuite a pu être "
                      "coupée en deux, le verdict ci-dessous n'est pas fiable.")

            # Vote : le juge n'est pas déterministe sur les cas limites, et
            # une faille qui apparaît selon le tirage n'a rien à faire dans
            # un rapport.
            verdict = juger_par_vote(payload["texte"], reponse)
            if piste:
                piste.consigner_verdict(numero, verdict)
            print(f"  [Arbitre]   enfreint={verdict['reussi']} "
                  f"({verdict['critere']}, votes {verdict['votes']}) : "
                  f"{verdict['analyse']}\n")

            # Ce que cet échange nous apprend, pour le choix du prochain
            # essai. Enregistré AVANT tout `continue` : un échec instruit
            # autant qu'un succès, et c'est même sa seule utilité.
            observations = cumuler(observations,
                                   observer(payload, reponse, verdict))

            # Un verdict illisible (None) n'est PAS une faille : on continue.
            if verdict["reussi"] is not True:
                continue

            # --- 4. Vérification par rejeu, si une valeur a été divulguée --
            verification = None
            if verdict["critere"] == "divulgation":
                # Le rejeu reçoit `juger` sans vote : il interroge déjà la
                # cible plusieurs fois, ce qui lisse le bruit. Voter en plus
                # coûterait neuf appels là où trois suffisent.
                verification = verifier_par_rejeu(
                    payload["texte"], verdict["valeur"],
                    piste.tracer("rejeu", interroger_cible) if piste
                    else interroger_cible,
                    juger,
                )
                print(f"  [Rejeu]     {verification['statut']} : "
                      f"{verification['explication']}")

                if verification["statut"] == "hallucination_probable":
                    # La cible a inventé : rien n'a fuité, pas de constat.
                    print("  >>> Valeur inventée par la cible : on continue.\n")
                    continue
        except BudgetDepasse as arret:
            # Arrêt NORMAL, pas une panne : on garde ce qui a été trouvé
            # jusqu'ici, et on dira franchement que le plan n'est pas allé
            # à son terme. L'essai en cours est perdu, c'est assumé.
            ecourtee = str(arret)
            print(f"\n>>> {arret}")
            print(f">>> Campagne ÉCOURTÉE à l'essai {numero} sur "
                  f"{MAX_ESSAIS}.")
            break

        print("  >>> Constat retenu.\n")
        constats.append({
            "essai": numero,
            "payload": payload,
            "reponse": reponse,
            "verdict": verdict,
            # None (obéissance, pas de valeur), ou le résultat du rejeu :
            # "confirmee", "contradictoire", "inconcluant"…
            "verification": verification,
            "tronquee": tronquee,
        })

    if not ecourtee:
        print(f">>> Budget d'essais épuisé : {len(constats)} constat(s).")

    return _terminer({
        # Un plan écourté ne doit JAMAIS se présenter comme un plan terminé :
        # « aucun constat » n'a pas le même sens dans les deux cas.
        "statut": ("budget_epuise" if ecourtee
                   else "constats" if constats else "aucun_constat"),
        "fiche": fiche,
        "plan": plan,
        "constats": constats,
        # Les essais RÉELLEMENT envoyés, et ce qu'on a appris en route. C'est
        # d'eux que le rapport tire sa couverture : depuis l'adaptation, le
        # plan initial n'est plus ce qui a été lancé, et annoncer la
        # couverture du plan serait un mensonge par omission.
        "lances": lances,
        "observations": observations,
        "ecourtee": ecourtee,
    })


def _terminer(resultat):
    """Attache le journal des appels et avertit si des réponses ont été coupées."""
    resultat.setdefault("ecourtee", None)
    resultat.setdefault("lances", [])
    resultat.setdefault("observations", [])
    resultat.setdefault("payloads", _provenance_des_payloads())
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


def _provenance_des_payloads():
    """Avec quelle bibliothèque la campagne a travaillé, et de quand date-t-elle."""
    from agents.attaquant import AGE_INSTANTANE_SUSPECT, charger_bibliotheque

    garak = charger_bibliotheque().get("_garak")
    if not garak:
        return None
    age = garak.get("age_jours")
    return {**garak,
            "perime": age is not None and age > AGE_INSTANTANE_SUSPECT}


def cli(arguments=None):
    """Point d'entrée en ligne de commande (voir [project.scripts])."""
    parseur = argparse.ArgumentParser(description="Lance une campagne de test.")
    parseur.add_argument(
        "--cible", default=None,
        help="'leurre' (défaut), 'mock', ou une URL http(s). "
             "Sinon la valeur de CIBLE dans .env.")
    parseur.add_argument(
        "--rapport", nargs="?", const="rapports", default=None,
        metavar="DOSSIER",
        help="écrire resultat.json et rapport.md dans DOSSIER "
             "(par défaut : rapports/).")
    parseur.add_argument(
        "--abreger", action="store_true",
        help="tronquer payloads et réponses dans rapport.md (pour partager "
             "un rapport sans réponses verbatim, ou publier un exemple). "
             "resultat.json garde tout.")
    parseur.add_argument(
        "--contexte", default="", metavar="LISTE",
        help="ce que l'application AUTOUR de la cible fait de sa sortie, "
             "séparé par des virgules : "
             + ", ".join(CONTEXTES_CONNUS)
             + ". Certaines familles de sondes n'ont aucun sens sans ça, et "
               "une cible ne peut pas le déclarer elle-même.")
    parseur.add_argument(
        "--autorisation", default=FICHIER_AUTORISATION, metavar="FICHIER",
        help=f"mandat couvrant la cible (défaut : {FICHIER_AUTORISATION}). "
             f"Inutile pour une cible locale.")
    arguments = parseur.parse_args(arguments)

    nom_cible = arguments.cible or CIBLE

    # Un nom de contexte inconnu est une FAUTE DE FRAPPE, pas un contexte
    # absent : l'accepter en silence écarterait des familles entières sans que
    # personne comprenne pourquoi. Même logique que le profil inconnu, qui
    # échoue dès l'import avec la liste des valeurs valides.
    contexte = [c.strip() for c in arguments.contexte.split(",") if c.strip()]
    inconnus = [c for c in contexte if c not in CONTEXTES_CONNUS]
    if inconnus:
        print(f"Contexte inconnu : {', '.join(inconnus)}.\n"
              f"Valeurs acceptées : {', '.join(CONTEXTES_CONNUS)}.",
              file=sys.stderr)
        raise SystemExit(2)

    # Le mandat AVANT tout : on ne lance pas une seule requête vers un
    # système tiers sans pouvoir prouver qu'on en avait le droit.
    try:
        autorisation = exiger(nom_cible, arguments.autorisation)
    except AutorisationManquante as refus:
        # Une consigne, pas une trace : le lecteur doit savoir quoi faire.
        print(f"Campagne REFUSÉE.\n{refus}", file=sys.stderr)
        raise SystemExit(2)

    if autorisation:
        print(f"Mandat : {autorisation['reference']} — "
              f"autorisé par {autorisation['autorise_par']}, "
              f"du {autorisation['debut']} au {autorisation['fin']}.\n")

    dossier = arguments.rapport or "rapports"
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    # La piste d'audit est écrite TOUJOURS, même sans --rapport : elle est
    # la trace de ce qu'on a envoyé, pas un livrable optionnel.
    piste = PisteAudit(Path(dossier) / f"{horodatage}-journal.jsonl",
                       nom_cible, autorisation)

    try:
        resultat = lancer_campagne(
            choisir_cible(arguments.cible), nom_cible, piste, contexte)
    finally:
        # Même si la campagne lève, le journal doit se refermer proprement.
        piste.clore(locals().get("resultat", {}).get("statut", "interrompue"),
                    journal())

    resultat["autorisation"] = autorisation
    print(f"\nRésultat final : {resultat['statut']}")
    print(f"Piste d'audit : {piste.chemin}")

    if arguments.rapport:
        chemin_json, chemin_md = enregistrer(
            resultat, cible=nom_cible, dossier=arguments.rapport,
            abreger=arguments.abreger)
        print(f"Rapport écrit : {chemin_md}\n"
              f"Source de vérité : {chemin_json}")

    return resultat


if __name__ == "__main__":
    cli()
