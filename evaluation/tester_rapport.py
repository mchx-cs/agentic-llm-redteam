"""
evaluation/tester_rapport.py — Teste la construction du rapport.

Aucun LLM : la gravité vient de règles déterministes, et le rendu d'un
gabarit. Tout est donc vérifiable instantanément et gratuitement.

Ce qui est vérifié :
- chaque combinaison (critère, rejeu) donne la bonne gravité ;
- les constats sont triés du plus grave au moins grave ;
- la couverture distingue les techniques même quand elles partagent une
  famille OWASP ;
- un rapport sans constat invite à lire la couverture, au lieu de laisser
  croire que la cible est sûre ;
- une réponse tronquée est signalée dans le constat.

Lance-le depuis la racine du projet avec :
    python -m evaluation.tester_rapport
"""

from rapport import construire, evaluer_gravite, rendre_markdown


def _payload(technique="t", famille="LLM02", texte="payload"):
    return {"technique": technique, "famille_owasp": famille,
            "objectif": "secret", "transformation": "identite", "texte": texte}


def _verdict(critere, valeur=None):
    return {"reussi": True, "critere": critere, "valeur": valeur,
            "analyse": "analyse", "votes": [True, True, True]}


def _constat(critere, statut_rejeu, tronquee=False, famille="LLM02"):
    rejeu = ({"statut": statut_rejeu, "explication": "explication"}
             if statut_rejeu else None)
    return {"essai": 1, "payload": _payload(famille=famille),
            "reponse": "réponse de la cible", "verdict": _verdict(critere, "V"),
            "verification": rejeu, "tronquee": tronquee}


def _verifier(titre, obtenu, attendu):
    ok = attendu(obtenu) if callable(attendu) else attendu == obtenu
    print(f"[{'ok ' if ok else 'ERR'}] {titre}")
    if not ok:
        print(f"      obtenu : {str(obtenu)[:160]}")
    return ok


def tester():
    resultats = []

    # --- Les règles de gravité ------------------------------------------
    attendus = {
        ("divulgation", "confirmee"): "elevee",
        ("divulgation", "contradictoire"): "a_verifier",
        ("divulgation", "inconcluant"): "a_verifier",
        ("divulgation", "non_verifiable"): "moyenne",
        ("obeissance", None): "moyenne",
    }
    for (critere, statut), gravite in attendus.items():
        rejeu = {"statut": statut, "explication": ""} if statut else None
        obtenu, _ = evaluer_gravite(_verdict(critere), rejeu, False)
        resultats.append(_verifier(
            f"gravité ({critere}, {statut}) = {gravite}", obtenu, gravite))

    # Un cas imprévu ne doit pas faire tomber le rapport, ni être minimisé.
    obtenu, _ = evaluer_gravite(_verdict("critere_inconnu"), None, False)
    resultats.append(_verifier(
        "un critère inconnu retombe sur 'à vérifier'", obtenu, "a_verifier"))

    # Une réponse coupée est signalée, mais ne change pas la gravité.
    gravite, pourquoi = evaluer_gravite(
        _verdict("obeissance"), None, tronquee=True)
    resultats.append(_verifier(
        "une réponse tronquée est signalée dans la justification",
        (gravite, "tronquée" in pourquoi), ("moyenne", True)))

    # --- Le tri -----------------------------------------------------------
    resultat = {
        "statut": "constats", "fiche": None,
        "plan": {"essais": [_payload()], "ecartees": []},
        "constats": [
            _constat("obeissance", None),                 # moyenne
            _constat("divulgation", "inconcluant"),       # à vérifier
            _constat("divulgation", "confirmee"),         # élevée
        ],
        "journal": {"appels": 3, "tokens": 100, "tronquees": []},
    }
    rapport = construire(resultat, cible="essai")
    resultats.append(_verifier(
        "les constats sont triés du plus grave au moins grave",
        [c["gravite"] for c in rapport["constats"]],
        ["elevee", "moyenne", "a_verifier"]))

    # --- La couverture ------------------------------------------------------
    resultat_couverture = {
        "statut": "aucun_constat", "fiche": None,
        "plan": {"essais": [], "ecartees": [
            # Deux techniques, une seule famille : le rendu doit les
            # distinguer, sinon il affiche deux lignes identiques.
            {"technique": "injection-directe", "famille_owasp": "LLM01",
             "motifs": ["aucun modèle"]},
            {"technique": "jailbreak", "famille_owasp": "LLM01",
             "motifs": ["aucun modèle"]},
        ]},
        "constats": [], "journal": {},
    }
    texte = rendre_markdown(construire(resultat_couverture, cible="essai"))
    resultats.append(_verifier(
        "deux techniques d'une même famille restent distinctes",
        texte, lambda t: "injection-directe" in t and "jailbreak" in t))
    resultats.append(_verifier(
        "sans constat, le rapport renvoie à la couverture",
        texte, lambda t: "avant d'en conclure que la cible est sûre" in t))

    # --- Le rendu complet ---------------------------------------------------
    texte_complet = rendre_markdown(rapport)
    for attendu in ("# Rapport de campagne", "## Constats", "## Couverture",
                    "Élevée", "C01"):
        resultats.append(_verifier(f"le rendu contient « {attendu} »",
                                   texte_complet, lambda t, a=attendu: a in t))

    print(f"\n{sum(resultats)}/{len(resultats)} vérifications conformes.")
    return all(resultats)


if __name__ == "__main__":
    tester()
