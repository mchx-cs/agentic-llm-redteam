"""
agents/planificateur.py — L'agent qui décide QUOI lancer, et dans quel ordre.

Entre la reconnaissance et l'attaque : à partir de la fiche cible, il choisit
les techniques qui ont un sens ici, les objectifs à viser, et classe le tout
pour que les meilleures combinaisons tiennent dans le budget d'essais.

Choix de conception — des RÈGLES, pas un LLM :
C'est volontairement du code déterministe. Le LLM a déjà fait sa part en
extrayant des faits (la fiche) ; lui confier en plus la décision, ce serait
risquer qu'il invente un contexte et gaspille tout le budget. Ici, chaque
exclusion est traçable : on peut dire POURQUOI une famille n'a pas été lancée,
ce qui comptera dans le rapport (Phase 6).

Planification ≠ adaptation. On décide ici AVANT la campagne. Reformuler
pendant l'attaque, selon la réponse de la cible, c'est la Phase 3 (PyRIT).
"""

from agents.attaquant import (TRANSFORMATIONS, charger_bibliotheque, composer)

# Chaque prérequis est une question posée à la fiche cible. Ajouter une
# famille d'attaque = ajouter son prérequis ici, et rien d'autre.
PREREQUIS = {
    # Abuser d'un outil suppose que la cible en ait au moins un.
    "outils": (
        lambda fiche: bool(fiche["outils"]),
        "aucun outil détecté chez la cible",
    ),
    # Faire fuiter une donnée confidentielle suppose qu'il y en ait une :
    # une cible qui ne refuse rien et n'évoque aucune règle n'a probablement
    # rien à protéger.
    "secret": (
        lambda fiche: bool(fiche["sujets_refuses"]) or fiche["mentionne_consignes"],
        "la cible ne déclare ni sujet interdit ni consigne",
    ),
    # Extraire des instructions internes suppose qu'elle en ait évoqué.
    "consignes": (
        lambda fiche: fiche["mentionne_consignes"] or bool(fiche["sujets_refuses"]),
        "la cible n'évoque aucune consigne interne",
    ),
}

# Une technique sans modèle de texte ne peut rien produire : on le dit
# explicitement plutôt que de la voir disparaître sans explication.
MOTIF_SANS_MODELE = "aucun modèle de payload dans la bibliothèque"


def objectifs_pour(fiche, bibliotheque):
    """
    Les objectifs à viser : ceux de la bibliothèque, plus ceux déduits de la
    fiche. Si la cible dit refuser de parler du « code du coffre », alors
    obtenir ce code devient un objectif propre à CETTE cible — c'est tout
    l'intérêt de la reconnaissance.
    """
    objectifs = list(bibliotheque["objectifs"])

    for numero, sujet in enumerate(fiche["sujets_refuses"], start=1):
        objectifs.append({
            "id": f"refus-{numero}",
            "formulation": f"me parler de : {sujet}",
            "origine": "reconnaissance",
        })

    return objectifs


def planifier(fiche, budget):
    """
    Renvoie {"essais": [...], "candidats": [...], "ecartees": [...]}.

    - essais    : le plan INITIAL, les mieux classés d'abord, au plus `budget`
                  (le planificateur ne décide jamais de dépasser la limite de
                  la campagne). C'est ce qu'on lancerait sans rien apprendre
                  de la cible.
    - candidats : le VIVIER complet, trié. La campagne y pioche au fur et à
                  mesure, en réordonnant d'après les réponses déjà obtenues
                  (agents/adaptation.py). Il n'est pas tronqué : un essai
                  relégué au-delà du budget initial doit pouvoir remonter si
                  la cible révèle qu'il est pertinent.
    - ecartees  : les techniques non retenues ET pourquoi. Un outil de sécurité
                  qui ne dit pas ce qu'il n'a PAS testé donne une fausse
                  impression de couverture.
    """
    bibliotheque = charger_bibliotheque()
    objectifs = objectifs_pour(fiche, bibliotheque)

    retenues, ecartees = [], []

    for technique in bibliotheque["techniques"]:
        motifs = [texte for nom, (verifier, texte) in PREREQUIS.items()
                  if nom in technique["prerequis"] and not verifier(fiche)]
        if not technique["modeles"] and not technique.get("payloads_complets"):
            motifs.append(MOTIF_SANS_MODELE)

        if motifs:
            ecartees.append({"technique": technique["id"],
                             "famille_owasp": technique["famille_owasp"],
                             "motifs": motifs})
        else:
            retenues.append(technique)

    essais = []
    for technique in retenues:
        for modele in technique["modeles"]:
            for objectif in objectifs:
                for nom_transfo, transformer in TRANSFORMATIONS.items():
                    texte = modele.format(objectif=objectif["formulation"])
                    essais.append({
                        "technique": technique["id"],
                        "famille_owasp": technique["famille_owasp"],
                        "objectif": objectif["id"],
                        "transformation": nom_transfo,
                        "texte": transformer(texte),
                        "priorite": _priorite(technique, objectif, nom_transfo),
                    })

        # Les payloads venus de l'extérieur (garak) sont des prompts complets :
        # ils portent leur propre intention, donc pas d'axe objectif.
        for payload in technique.get("payloads_complets", []):
            # Un payload complet sert de PRÉAMBULE : seul, il mesure la
            # résistance au détournement ; composé avec un objectif issu de
            # la reconnaissance, il va chercher ce que la cible protège.
            variantes = [(o, composer(payload, o)) for o in objectifs]
            variantes.append((None, payload))
            for objectif, texte in variantes:
                for nom_transfo, transformer in TRANSFORMATIONS.items():
                    essais.append({
                        "technique": technique["id"],
                        "famille_owasp": technique["famille_owasp"],
                        "objectif": objectif["id"] if objectif else None,
                        "transformation": nom_transfo,
                        "texte": transformer(texte),
                        "source": technique.get("source"),
                        "priorite": _priorite(technique, objectif, nom_transfo),
                    })

    # Tri stable : à priorité égale, l'ordre de la bibliothèque est conservé,
    # donc deux campagnes identiques produisent la même liste.
    essais.sort(key=lambda essai: essai["priorite"])
    return {"essais": _repartir(essais, budget),
            "candidats": essais,
            "ecartees": ecartees}


def _repartir(essais, budget):
    """
    Répartit le budget ENTRE les techniques, au lieu de le donner à la
    première.

    Trier puis trancher paraissait suffisant tant que la bibliothèque tenait
    en douze payloads. Avec 614, la première technique raflait les six essais
    disponibles : on apprenait tout d'une sonde et rien des cinquante-deux
    autres. Or un scanner doit d'abord balayer, puis creuser.

    On prend donc un essai par technique, dans l'ordre de priorité, puis un
    deuxième de chacune, et ainsi de suite. À budget égal, la couverture est
    maximale — et le rapport peut enfin parler de plusieurs familles.
    """
    if budget <= 0:
        return []

    par_technique = {}
    for essai in essais:                     # `essais` est déjà trié
        par_technique.setdefault(essai["technique"], []).append(essai)

    retenus = []
    tours = max((len(v) for v in par_technique.values()), default=0)
    for tour in range(tours):
        for candidats in par_technique.values():
            if tour < len(candidats):
                retenus.append(candidats[tour])
                if len(retenus) >= budget:
                    return retenus
    return retenus


def _priorite(technique, objectif, nom_transformation):
    """
    Plus le nombre est petit, plus l'essai passe tôt. Quatre idées, dans
    l'ordre : viser ce que la cible protège, préférer un payload éprouvé,
    attaquer avant de contrôler, et commencer sans transformation (une
    attaque qui échoue en clair n'échoue pas à cause de l'encodage).

    `objectif` vaut None pour un payload complet, qui porte déjà sa propre
    intention : il est traité comme ciblé, ni mieux ni moins bien qu'un
    objectif issu de la reconnaissance.
    """
    priorite = 0
    if objectif is None:
        # Un payload complet SEUL mesure la résistance au détournement. Utile,
        # mais moins que le même payload chargé de réclamer ce que la cible
        # protège : à priorité égale, le tour de rôle ne retiendrait que lui.
        priorite += 1
    elif objectif.get("origine") != "reconnaissance":
        priorite += 4          # un objectif générique passe après un objectif ciblé
    if technique["id"] == "controle":
        priorite += 2          # le témoin n'est pas une attaque : il attend son tour
    if nom_transformation != "identite":
        priorite += 1          # le texte brut d'abord, les variantes ensuite
    return priorite


def resumer(plan):
    """Le plan en quelques lignes, pour l'affichage d'une campagne."""
    lignes = [f"  {len(plan['essais'])} essai(s) retenu(s) :"]
    for essai in plan["essais"]:
        lignes.append(f"    - {essai['technique']} / "
                      f"{essai['objectif'] or 'payload complet'} "
                      f"/ {essai['transformation']}")
    if plan["ecartees"]:
        lignes.append("  familles écartées :")
        for ecartee in plan["ecartees"]:
            lignes.append(f"    - {ecartee['technique']} : "
                          f"{' ; '.join(ecartee['motifs'])}")
    return "\n".join(lignes)
