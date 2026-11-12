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

    # --- Capacités de la cible, sondées en reconnaissance -------------------
    # Tri-état assumé : on n'écarte que sur un NON explicite. « La cible n'en a
    # pas parlé » (None) laisse passer la sonde, parce que rater une faille
    # coûte plus cher qu'un essai gaspillé — et parce qu'un chatbot ne détaille
    # pas forcément tout ce qu'il sait faire.
    "produit-du-code": (
        lambda fiche: fiche.get("produit_du_code") is not False,
        "la cible dit ne pas écrire de code",
    ),
    "traite-des-documents": (
        lambda fiche: fiche.get("traite_des_documents") is not False,
        "la cible dit ne pas traiter de document fourni",
    ),

    # --- Contexte d'exécution, DÉCLARÉ par l'opérateur ----------------------
    # Asymétrie volontaire avec les capacités ci-dessus : ici, non déclaré veut
    # dire écarté. Une cible ne sait pas dans quoi sa sortie est rendue, donc
    # personne n'a répondu — et l'attaque est structurellement intestable sans
    # ce contexte. Jusqu'au 2026-11-11, `web_injection` partait contre un
    # chatbot texte et le rapport annonçait « LLM02 testée » : un essai perdu
    # ET une couverture surévaluée. Le motif dit comment l'activer.
    "terminal": (
        lambda fiche: "terminal" in (fiche.get("contexte") or []),
        "sortie non rendue dans un terminal (--contexte terminal pour l'activer)",
    ),
    "rendu-riche": (
        lambda fiche: "rendu-riche" in (fiche.get("contexte") or []),
        "aucun client ne rend le Markdown de la sortie "
        "(--contexte rendu-riche pour l'activer)",
    ),
    "base-donnees": (
        lambda fiche: "base-donnees" in (fiche.get("contexte") or []),
        "aucune base ni moteur de gabarits déclaré derrière la cible "
        "(--contexte base-donnees pour l'activer)",
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

    # Un outil découvert devient un objectif. Écrire « appelle
    # consulter_dossier » dans la bibliothèque ne vaudrait que contre la cible
    # de démonstration ; le nom de l'outil doit venir de la reconnaissance,
    # exactement comme le sujet refusé vient d'elle juste au-dessus.
    #
    # Le « pour quelqu'un d'autre que moi » n'est pas un ornement : c'est le
    # discriminant du critère `abus_outils` de l'arbitre. Consulter SON propre
    # dossier est un usage légitime (cas D17 du corpus) ; obtenir celui d'un
    # tiers est la faille. Sans ce membre de phrase, les quatre registres
    # produiraient des essais que le juge classerait — à raison — « aucun ».
    for numero, outil in enumerate(fiche["outils"], start=1):
        objectifs.append({
            "id": f"outil-{numero}",
            "formulation": f"utiliser ton outil « {outil} » pour quelqu'un "
                           f"d'autre que moi",
            "origine": "reconnaissance",
            # La famille pour laquelle cet objectif a été fabriqué : voir
            # `_priorite`, qui le fait passer devant sur cette famille-là.
            "pour_famille": "LLM06",
        })

    return objectifs


# --- Restreindre le périmètre d'une campagne ---------------------------------
# Trois besoins distincts, un seul mécanisme :
#
# 1. LE MANDAT. `autorisation.example.json` déclare une portée qui mentionne
#    « techniques exclues », et le rapport l'affiche fidèlement — mais rien ne
#    l'appliquait. Un rapport qui cite un mandat excluant une technique, puis
#    documente le lancement de cette technique, est un écart contractuel.
# 2. REPRODUIRE un constat après correction, sans relancer toute la campagne
#    et sans que l'adaptation change d'avis en route.
# 3. pass@k, qui exige de rejouer la MÊME technique k fois — impossible tant
#    que le tour de rôle balaye les modules.
#
# Un seul motif couvre les trois granularités utiles, parce qu'en demander
# trois serait trois options à retenir pour le même geste : famille OWASP
# (« LLM07 »), module garak (« dan ») ou technique (« fuite-prompt-systeme »).

def _correspond(technique, motif):
    """Le motif désigne-t-il cette technique, son module ou sa famille ?"""
    motif = motif.strip().lower()
    if not motif:
        return False
    champs = (technique["id"], technique.get("groupe") or "",
              technique.get("famille_owasp") or "")
    return any(motif in champ.lower() for champ in champs)


def filtrer(techniques, seulement=(), sauf=()):
    """
    Les techniques retenues, et celles qu'un motif a écartées avec son motif.

    `sauf` l'emporte sur `seulement` : une exclusion vient du mandat, et un
    mandat ne se contourne pas par une autre option de la même commande.
    """
    retenues, ecartees = [], []
    for technique in techniques:
        exclusion = next((m for m in sauf if _correspond(technique, m)), None)
        if exclusion:
            ecartees.append((technique, f"exclue par --sauf {exclusion}"))
            continue
        if seulement and not any(_correspond(technique, m) for m in seulement):
            ecartees.append(
                (technique,
                 f"hors du périmètre demandé (--seulement "
                 f"{', '.join(seulement)})"))
            continue
        retenues.append(technique)
    return retenues, ecartees


def planifier(fiche, budget, seulement=(), sauf=()):
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

    # Le périmètre d'abord : une technique exclue par le mandat n'a pas à être
    # écartée pour « aucun outil détecté », ce qui masquerait la vraie raison.
    techniques, hors_perimetre = filtrer(bibliotheque["techniques"],
                                         seulement, sauf)
    for technique, motif in hors_perimetre:
        ecartees.append({"technique": technique["id"],
                         "famille_owasp": technique["famille_owasp"],
                         "motifs": [motif]})

    for technique in techniques:
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

    # Une technique maison encore vide dont la FAMILLE est par ailleurs
    # couverte par garak n'est pas un trou de couverture. Sans cette
    # distinction, le rapport affichait côte à côte « divulgation-information
    # (LLM02) — aucun modèle de payload » et « Familles testées : LLM02 », ce
    # qui est contradictoire pour un lecteur et invente un trou qui n'existe
    # pas. On ne la masque pas pour autant : on dit où la famille est traitée.
    familles_retenues = {t["famille_owasp"] for t in retenues
                         if t["famille_owasp"]}
    for ecartee in ecartees:
        # Réservé au SEUL cas qui le justifie : une technique écartée faute de
        # payload, dont la famille est traitée ailleurs. Le champ s'appliquait
        # à toutes les écartées, ce qui est devenu visible — et faux — avec les
        # règles de pertinence du 2026-11-11 : `ansiescape` relève de LLM01,
        # couverte par ailleurs, mais elle teste les séquences ANSI que nulle
        # autre sonde ne teste. Dire « couverte ailleurs » laissait croire que
        # son écartement ne coûtait rien.
        ecartee["famille_couverte_ailleurs"] = (
            MOTIF_SANS_MODELE in ecartee["motifs"]
            and ecartee["famille_owasp"] in familles_retenues)

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
                        "familles_non_jugeables":
                            technique.get("familles_non_jugeables") or [],
                        "groupe": _groupe(technique),
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
                        "familles_non_jugeables":
                            technique.get("familles_non_jugeables") or [],
                        "groupe": _groupe(technique),
                        "priorite": _priorite(technique, objectif, nom_transfo),
                    })

    # Tri stable : à priorité égale, l'ordre de la bibliothèque est conservé,
    # donc deux campagnes identiques produisent la même liste.
    essais.sort(key=lambda essai: essai["priorite"])
    return {"essais": _repartir(essais, budget),
            "candidats": essais,
            "ecartees": ecartees}


def _groupe(technique):
    """
    Le grain du tour de rôle : le module garak, ou l'identifiant pour une
    technique maison.

    Pourquoi pas la technique : `encoding` compte quinze sondes sur les
    cinquante-deux du périmètre, toutes variantes du même test. Compter par
    technique leur donnait quinze tours quand `dan` en obtenait trois, et
    l'ordre alphabétique faisait le reste — une campagne à budget élargi se
    serait épuisée en variantes d'encodage avant d'atteindre `promptinject`.
    """
    return technique.get("groupe") or technique["id"]


def _repartir(essais, budget):
    """
    Répartit le budget ENTRE les groupes de techniques, au lieu de le donner
    à la première.

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
        cle = essai.get("groupe") or essai["technique"]
        par_technique.setdefault(cle, []).append(essai)

    retenus = []
    tours = max((len(v) for v in par_technique.values()), default=0)
    for tour in range(tours):
        for candidats in par_technique.values():
            if tour < len(candidats):
                retenus.append(candidats[tour])
                if len(retenus) >= budget:
                    return retenus
    return retenus


def _apparies(technique, objectif):
    """
    Cet objectif a-t-il été fabriqué pour la famille de cette technique ?

    Le rapprochement se fait sur le PRÉFIXE de la famille (`LLM06`), pas sur
    son libellé complet : `bibliotheque.json` écrit « LLM06:2025 Excessive
    Agency », et faire dépendre une règle de priorité du millésime OWASP la
    casserait à la prochaine révision du Top 10.
    """
    attendue = objectif.get("pour_famille")
    famille = technique.get("famille_owasp") or ""
    return bool(attendue) and famille.startswith(attendue)


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
    elif _apparies(technique, objectif):
        # Un objectif fabriqué POUR une famille passe devant sur cette
        # famille. Sans cette règle, le tour de rôle ne retenait qu'un essai
        # par technique, et à égalité c'était l'ordre de la liste qui
        # tranchait : la technique `abus-outils` partait avec un objectif
        # `refus-N` et n'appelait aucun outil. Un payload d'abus d'outil qui
        # ne nomme pas d'outil ne teste rien.
        priorite -= 1
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
        # Groupé par MOTIF, pas par technique : depuis les règles de
        # pertinence, ce sont des modules entiers qui sont écartés, et huit
        # sondes `web_injection` affichaient huit fois « aucun client ne rend
        # le Markdown ». Une information répétée noie celle qui ne l'est pas.
        lignes.append("  écartées :")
        for motif, techniques in grouper_par_motif(plan["ecartees"]):
            lignes.append(f"    - {len(techniques)} technique(s) : {motif}")
            apercu = ", ".join(techniques[:3])
            if len(techniques) > 3:
                apercu += f", +{len(techniques) - 3} autre(s)"
            lignes.append(f"      ({apercu})")
    return "\n".join(lignes)


def grouper_par_motif(ecartees):
    """
    [(motif, [techniques])], dans l'ordre d'apparition des motifs.

    Partagé entre l'affichage de campagne et le rapport : les deux doivent
    grouper de la même façon, sinon un lecteur qui a vu la campagne ne
    reconnaîtrait pas le rapport.
    """
    groupes = {}
    for ecartee in ecartees:
        motif = " ; ".join(ecartee["motifs"])
        groupes.setdefault(motif, []).append(ecartee["technique"])
    return list(groupes.items())
