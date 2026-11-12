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
                   exiger, telemetrie)
from agents.adaptation import cumuler, observer, prochain
from agents.arbitre import juger, juger_par_vote
from agents.planificateur import planifier, resumer as resumer_plan
from agents.reconnaissance import (CONTEXTES_CONNUS, reconnaitre,
                                    resumer as resumer_fiche)
from agents.verificateur import verifier_par_rejeu
from cibles import choisir_cible
from cibles.http import PROFILS_CIBLE, tester as tester_cible_http
from config import BUDGET_APPELS, BUDGET_TOKENS, CIBLE
from llm_client import BudgetDepasse, journal, reinitialiser_journal
from rapport import enregistrer

# Règle d'arrêt : on ne tente pas une attaque à l'infini.
MAX_ESSAIS = 3


def lancer_campagne(interroger_cible=None, nom_cible=None, piste=None,
                    contexte=(), adaptatif=True, seulement=(), sauf=()):
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
    plan = planifier(fiche, MAX_ESSAIS, seulement, sauf)
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
    etats = []              # l'issue de chacun : scorable ou non (ASR)
    ecourtee = None
    print()
    for numero in range(1, MAX_ESSAIS + 1):
        # `adaptatif=False` rejoue le plan statique : même vivier, même
        # ordre de priorité, mais sans rien apprendre des réponses. C'est le
        # TÉMOIN dont la mesure du gain a besoin — sans lui, on ne peut
        # comparer l'adaptation qu'à des campagnes simulées.
        payload = prochain(plan["candidats"],
                           observations if adaptatif else (), lances)
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

            # Un verdict illisible (None) n'est PAS une faille — mais ce
            # n'est pas non plus une victoire de la cible. Les confondre
            # gonflait sa solidité apparente : un juge qui ne tranche pas est
            # une mesure MANQUANTE, pas un refus. L'essai est donc exclu du
            # dénominateur de l'ASR (manuel OWASP §7.5), et compté à part.
            if tronquee:
                etats.append("reponse_tronquee")
                continue
            if verdict["reussi"] is None:
                etats.append("juge_indecis")
                continue
            if verdict["reussi"] is False:
                etats.append("resiste")
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
                    # Scorable malgré tout — l'attaque a bien échoué, et le
                    # rejeu l'a établi plutôt que de le supposer.
                    etats.append("hallucination")
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
        etats.append("faille")
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
        # L'issue de chaque essai, pour que le rapport calcule un ASR sur un
        # dénominateur DÉFINI plutôt que sur le nombre d'envois.
        "etats": etats,
        # Le périmètre demandé : le rapport DOIT le dire, sinon une campagne
        # restreinte à une famille présenterait sa couverture comme complète.
        "perimetre": {"seulement": list(seulement), "sauf": list(sauf)},
        # Les essais sont-ils i.i.d. ? Deux conditions, toutes deux
        # nécessaires : pas d'adaptation (sinon le prochain dépend des
        # réponses précédentes) et une seule technique lancée (sinon des
        # payloads de familles différentes ne partagent pas la même
        # probabilité de succès). Quand les deux sont vraies — typiquement
        # `--seulement X --sans-adaptation` — le rapport peut enfin borner son
        # « aucun constat », ce qui est précisément ce que pass@k demande.
        "essais_independants": (
            not adaptatif
            and len({e["technique"] for e in lances}) <= 1
            and len(lances) > 0),
        "ecourtee": ecourtee,
    })


def _terminer(resultat):
    """Attache le journal des appels et avertit si des réponses ont été coupées."""
    resultat.setdefault("ecourtee", None)
    resultat.setdefault("lances", [])
    resultat.setdefault("etats", [])
    resultat.setdefault("perimetre", {"seulement": [], "sauf": []})
    resultat.setdefault("essais_independants", False)
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


def perimetre(valeur):
    """Découpe « dan, encoding » en motifs propres, sans vide ni doublon."""
    vus, motifs = set(), []
    for motif in (valeur or "").split(","):
        motif = motif.strip()
        if motif and motif.lower() not in vus:
            vus.add(motif.lower())
            motifs.append(motif)
    return motifs


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
        "--seulement", default="", metavar="MOTIFS",
        help="restreindre la campagne, par famille OWASP (LLM07), module "
             "garak (dan) ou technique (fuite-prompt-systeme) ; plusieurs "
             "motifs séparés par des virgules. Le rapport dit toujours que "
             "la campagne était restreinte.")
    parseur.add_argument(
        "--sauf", default="", metavar="MOTIFS",
        help="écarter des techniques, mêmes motifs que --seulement. Sert à "
             "respecter une portée de mandat qui exclut des techniques ; "
             "l'emporte sur --seulement.")
    parseur.add_argument(
        "--sans-adaptation", action="store_true", dest="sans_adaptation",
        help="suivre le plan statique sans rien apprendre des réponses. "
             "Sert de témoin pour mesurer ce que l'adaptation apporte ; "
             "inutile en usage normal.")
    parseur.add_argument(
        "--profil-cible", default=None, metavar="NOM", dest="profil_cible",
        help="forme d'API de la cible, au lieu de décrire CIBLE_CORPS et "
             "CIBLE_CHEMIN_REPONSE à la main : "
             + ", ".join(PROFILS_CIBLE)
             + ". L'emporte sur CIBLE_CORPS et CIBLE_CHEMIN_REPONSE de .env : "
               "la ligne de commande est plus spécifique. Pour un corps sur mesure, "
               "règle .env et ne passe pas de profil.")
    parseur.add_argument(
        "--tester-cible", action="store_true", dest="tester_cible",
        help="envoyer UN message anodin pour vérifier le branchement, puis "
             "s'arrêter. Aucune attaque, aucun mandat requis : à lancer "
             "avant toute campagne contre une cible réelle.")
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

    # Le NOM de la cible d'abord, et c'est une correction : une faute de
    # frappe (« demo:9 », « leure ») sortait soit en trace Python, soit —
    # pire — en message d'autorisation, qui parlait de mandat à quelqu'un
    # qui s'était juste trompé de lettre. On vérifie donc le nom avant tout,
    # ce qui n'envoie aucune requête et ne touche pas à l'ordre du mandat.
    try:
        choisir_cible(nom_cible, arguments.profil_cible)
    except (ValueError, RuntimeError) as refus:
        print(f"Cible inutilisable.\n{refus}", file=sys.stderr)
        raise SystemExit(2)

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

    # Vérifier le branchement AVANT d'exiger le mandat, et avant de lancer
    # quoi que ce soit : c'est une requête anodine, pas un test d'intrusion.
    # L'ordre compte — découvrir une coquille de configuration ne doit pas
    # coûter une entrée dans la piste d'audit d'un client.
    if arguments.tester_cible:
        if not nom_cible.startswith(("http://", "https://")):
            print(f"--tester-cible vise une URL http(s) ; '{nom_cible}' est "
                  f"une cible livrée, qui n'a rien à configurer.",
                  file=sys.stderr)
            raise SystemExit(2)
        try:
            ok = tester_cible_http(nom_cible, profil=arguments.profil_cible)
        except RuntimeError as refus:
            print(refus, file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(0 if ok else 1)

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
                       nom_cible, autorisation,
                       contexte=telemetrie(nom_cible, arguments.profil_cible))

    try:
        resultat = lancer_campagne(
            choisir_cible(arguments.cible, arguments.profil_cible),
            nom_cible, piste, contexte,
            adaptatif=not arguments.sans_adaptation,
            seulement=perimetre(arguments.seulement),
            sauf=perimetre(arguments.sauf))
    except RuntimeError as panne:
        # La cible ne répond pas comme prévu : hôte injoignable, erreur HTTP,
        # réponse non-JSON, chemin de réponse erroné. Le message de
        # `cibles/http.py` dit déjà quoi corriger — il sortait seulement noyé
        # dans huit lignes de trace Python, alors que le projet tient à
        # donner une consigne. On y ajoute le raccourci qui évite de
        # recommencer à l'aveugle.
        print(f"\nCampagne INTERROMPUE : la cible n'a pas répondu comme "
              f"attendu.\n{panne}\n\n"
              f"Vérifie le branchement sans rien attaquer :\n"
              f"  python main.py --cible {nom_cible} --tester-cible",
              file=sys.stderr)
        print(f"Piste d'audit : {piste.chemin}", file=sys.stderr)
        raise SystemExit(1)
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
