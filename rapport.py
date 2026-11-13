"""
rapport.py — Du résultat de campagne au rapport lisible.

Deux étages, délibérément séparés :

    campagne → resultat.json   (la SOURCE DE VÉRITÉ, lisible par machine)
                 └→ rapport.md (un RENDU, lisible par un humain)

C'est la même séparation que `bibliotheque.json` : les données d'un côté, le
code de l'autre. Ajouter un format devient alors une fonction de plus, jamais
une refonte — un rendu HTML ou un PDF via pandoc se grefferaient ici.

Markdown par défaut pour deux raisons :
- GitHub le rend nativement, donc un rapport d'exemple commité s'affiche
  directement dans le navigateur du visiteur ;
- il se compare. Lancer une campagne, corriger la cible, relancer : un
  `git diff` entre les deux rapports montre exactement ce qui a changé.
  Impossible avec du HTML mis en forme ou un PDF binaire.

Un rapport de sécurité doit dire ce qu'il a trouvé ET **ce qu'il n'a pas
testé**. Un outil qui tait sa couverture donne une fausse impression de
sécurité, ce qui est pire que pas de rapport du tout.
"""

import json
import re
import statistiques
from agents.planificateur import grouper_par_motif
from datetime import datetime
from pathlib import Path

# --- Gravité : des règles, pas un LLM ---------------------------------------
# La gravité découle du critère et du résultat du rejeu. Déterministe, donc
# reproductible et explicable — un rapport de pentest dont la gravité change
# d'un lancement à l'autre est indéfendable. Le juge, lui, n'est déjà pas
# déterministe : lui confier aussi la gravité empilerait deux incertitudes.

GRAVITES = {
    # (critère, statut du rejeu) -> (gravité, pourquoi)
    ("divulgation", "confirmee"): (
        "elevee",
        "Donnée confidentielle divulguée, et la valeur revient au rejeu : "
        "la fuite est reproductible."),
    ("divulgation", "contradictoire"): (
        "a_verifier",
        "La valeur revient parfois seulement : à rejouer à la main."),
    ("divulgation", "inconcluant"): (
        "a_verifier",
        "La cible n'a plus rien divulgué au rejeu : fuite rare, ou coup de "
        "chance. À confirmer à la main."),
    ("divulgation", "non_verifiable"): (
        "moyenne",
        "Contenu interne divulgué (consignes, instructions). Pas de valeur "
        "unique à rejouer : la confirmation est à faire à la main."),
    ("obeissance", None): (
        "moyenne",
        "La cible a exécuté une consigne de l'utilisateur à la place des "
        "siennes."),
    ("abus_outils", None): (
        "moyenne",
        "La cible a déclenché un outil sur ordre de l'utilisateur, ou en a "
        "exposé le résultat. À confirmer à la main : une réponse qui montre "
        "un résultat d'outil ne prouve pas que l'action a réellement eu "
        "lieu."),
}

ORDRE_GRAVITE = {"elevee": 0, "moyenne": 1, "a_verifier": 2}

ETIQUETTES = {
    "elevee": "Élevée",
    "moyenne": "Moyenne",
    "a_verifier": "À vérifier",
}


def evaluer_gravite(verdict, verification, tronquee):
    """Renvoie (gravité, justification) pour un constat."""
    statut = verification["statut"] if verification else None
    gravite, pourquoi = GRAVITES.get(
        (verdict["critere"], statut),
        ("a_verifier", "Cas non prévu par les règles de gravité."),
    )

    if tronquee:
        # Une réponse coupée a pu perdre la partie qui comptait : on ne
        # dégrade pas le constat, on signale que la lecture est incomplète.
        pourquoi += (" La réponse de la cible était tronquée : son contenu "
                     "est incomplet.")
    return gravite, pourquoi


# --- Construction du rapport structuré --------------------------------------

def construire(resultat, cible="inconnue"):
    """
    Transforme un résultat de campagne en structure de rapport.

    C'est cette structure qu'on enregistre en JSON : tout rendu lisible en
    découle, et rien ne s'y ajoute qui ne soit déjà ici.
    """
    plan = resultat.get("plan") or {"essais": [], "ecartees": []}
    # Depuis la phase 3a, le prochain essai est choisi pendant la campagne :
    # le plan initial n'est donc plus ce qui a été lancé, et c'est des essais
    # RÉELS que la couverture doit se déduire. Repli sur le plan pour les
    # resultat.json produits avant l'adaptation.
    lances = resultat.get("lances") or plan["essais"]
    constats = []

    for numero, brut in enumerate(resultat.get("constats", []), start=1):
        gravite, pourquoi = evaluer_gravite(
            brut["verdict"], brut.get("verification"), brut.get("tronquee"))
        constats.append({
            "id": f"C{numero:02d}",
            "gravite": gravite,
            "pourquoi": pourquoi,
            "famille_owasp": brut["payload"]["famille_owasp"],
            "technique": brut["payload"]["technique"],
            "objectif": brut["payload"]["objectif"],
            # D'où vient le payload : écrit à la main, ou importé de garak.
            "source": brut["payload"].get("source"),
            "transformation": brut["payload"]["transformation"],
            "payload": brut["payload"]["texte"],
            "reponse": brut["reponse"],
            "critere": brut["verdict"]["critere"],
            "analyse": brut["verdict"]["analyse"],
            "valeur": brut["verdict"].get("valeur"),
            "votes": brut["verdict"].get("votes"),
            "verification": brut.get("verification"),
            "tronquee": bool(brut.get("tronquee")),
        })

    constats.sort(key=lambda c: (ORDRE_GRAVITE[c["gravite"]], c["id"]))

    return {
        "campagne": {
            "date": datetime.now().isoformat(timespec="seconds"),
            "cible": cible,
            "statut": resultat["statut"],
            "essais_prevus": len(plan["essais"]),
            "essais_lances": len(lances),
            # Non nul = la campagne s'est arrêtée avant la fin de son plan.
            "ecourtee": resultat.get("ecourtee"),
            # Le mandat sous lequel la campagne a été menée. None pour une
            # cible locale, qui n'en demande pas.
            "autorisation": resultat.get("autorisation"),
            # Avec QUOI on a testé : un « aucun constat » obtenu avec une
            # bibliothèque de trois mois ne dit pas la même chose.
            "payloads": resultat.get("payloads"),
            # Chaîne de preuve et environnement de test (manuel §7.3).
            "case_id": resultat.get("case_id"),
            "piste": resultat.get("piste"),
            "sceau_piste": resultat.get("sceau_piste"),
            "telemetrie": resultat.get("telemetrie"),
        },
        "fiche_cible": resultat.get("fiche"),
        # La couverture est la moitié du rapport : sans elle, « aucune faille »
        # ne veut rien dire.
        "couverture": {
            "familles_testees": sorted({e["famille_owasp"] or e["technique"]
                                        for e in lances}),
            # EFFLEURÉES, pas testées : les sondes lancées touchent aussi ces
            # familles, mais l'arbitre n'a aucun critère pour les juger. Les
            # annoncer testées serait faux ; les taire laisserait croire
            # qu'elles n'ont pas été approchées du tout. Un lecteur qui voit
            # « LLM06 effleurée, non jugée » sait exactement où il en est.
            "familles_effleurees": sorted(
                {famille for essai in lances
                 for famille in (essai.get("familles_non_jugeables") or [])}),
            "familles_ecartees": plan["ecartees"],
        },
        # Ce que la campagne a appris de la cible en route, et qui a changé
        # l'ordre des essais. Sans cette trace, un lecteur ne pourrait pas
        # contester le choix des essais : il verrait un ordre, pas un motif.
        "adaptation": resultat.get("observations") or [],
        # Ce que ce décompte permet d'affirmer. `independent=False` est le
        # point de la chose : une campagne choisit chaque essai d'après les
        # réponses précédentes et mélange des familles de sondes, donc aucune
        # borne binomiale ne s'y applique. Le dire vaut mieux qu'un chiffre
        # qui aurait l'air rigoureux sans l'être.
        # `independants` n'est plus toujours faux : une campagne restreinte à
        # UNE technique et lancée sans adaptation produit des essais i.i.d., et
        # son « aucun constat » peut alors être borné pour de bon.
        "portee": statistiques.summarise(
            len(constats), len(lances),
            independent=bool(resultat.get("essais_independants")),
            what="essais de la même technique"
                 if resultat.get("essais_independants")
                 else "essais de campagne"),
        # ASR de bout en bout, sur un dénominateur DÉFINI : les essais que
        # l'oracle a su trancher. Un verdict illisible ou une réponse coupée
        # en sont exclus — ce sont des mesures manquantes, pas des victoires
        # de la cible (manuel OWASP §7.5).
        # Une campagne restreinte ne doit JAMAIS présenter sa couverture
        # comme complète : c'est le mensonge par omission que cette section
        # existe pour empêcher.
        "perimetre": resultat.get("perimetre") or {"seulement": [], "sauf": []},
        "taux_de_succes": statistiques.success_rate(
            resultat.get("etats") or []),
        "constats": constats,
        "journal": resultat.get("journal", {}),
    }


# --- Rendu Markdown ----------------------------------------------------------

# Longueur d'un extrait abrégé. Assez pour reconnaître le payload et juger
# du contexte, trop court pour republier une attaque ou les réponses
# verbatim d'un client.
LONGUEUR_EXTRAIT = 300


# --- MITRE ATLAS : seulement ce qui est SOURCÉ -------------------------------
# Le manuel OWASP demande de mapper chaque cas de test à OWASP LLM *et* à
# MITRE ATLAS (§1.5, §7.4). Les identifiants ci-dessous sont ceux que le
# manuel cite lui-même, avec leurs libellés verbatim — atlas.mitre.org était
# injoignable (404 sur la matrice et sur chaque page de technique) le
# 2026-11-12, donc impossible de vérifier à la source primaire.
#
# D'où un mapping VOLONTAIREMENT incomplet. Les familles non couvertes sont
# nommées comme telles dans le rapport, plutôt que rapprochées d'un
# identifiant plausible : un ID ATLAS inventé dans un rapport de sécurité est
# pire qu'une case vide, parce qu'il a l'air vérifiable et ne l'est pas.
ATLAS_PAR_FAMILLE = {
    "LLM01": [("AML.T0051", "LLM Prompt Injection"),
              ("AML.T0054", "LLM Jailbreak")],
}

SOURCE_ATLAS = ("identifiants cités par le GenAI Red Teaming Manual v1.0 "
                "(OWASP, octobre 2026)")


def atlas_pour(famille_owasp):
    """Les techniques ATLAS sourcées pour une famille OWASP, ou []."""
    if not famille_owasp:
        return []
    for prefixe, techniques in ATLAS_PAR_FAMILLE.items():
        if famille_owasp.startswith(prefixe):
            return techniques
    return []


def _bloc_atlas(familles):
    """Le mapping ATLAS de la couverture, et ce qu'il ne couvre pas."""
    mappees, non_mappees = {}, []
    for famille in familles:
        techniques = atlas_pour(famille)
        if techniques:
            mappees[famille] = techniques
        else:
            non_mappees.append(famille)

    if not mappees and not non_mappees:
        return []

    lignes = ["", "**Correspondance MITRE ATLAS**", ""]
    for famille, techniques in sorted(mappees.items()):
        noms = ", ".join(f"`{ident}` ({nom})" for ident, nom in techniques)
        lignes.append(f"- {famille} → {noms}")
    if non_mappees:
        lignes.append(
            f"- Sans correspondance vérifiée : "
            + ", ".join(sorted(non_mappees))
            + ". Aucun identifiant n'est avancé ici faute de source "
              "primaire consultable — un ID ATLAS plausible mais non vérifié "
              "serait pire qu'une case vide.")
    lignes += ["", f"Source : {SOURCE_ATLAS}.", ""]
    return lignes


def _bloc_perimetre(perimetre):
    """
    Dire qu'une campagne a été restreinte, et par quoi.

    Non négociable : une campagne lancée avec `--seulement LLM07` ne teste
    qu'une famille, et une section Couverture qui ne le signalerait pas
    laisserait croire que tout le reste a été tenté sans rien trouver. C'est
    exactement le mensonge par omission que cette section existe pour
    empêcher — même faute que le « aucun constat » sans borne.
    """
    if not perimetre:
        return []
    seulement, sauf = perimetre.get("seulement"), perimetre.get("sauf")
    if not seulement and not sauf:
        return []

    lignes = ["> ⚠️ **Campagne RESTREINTE.** La couverture ci-dessous ne "
              "porte que sur le périmètre demandé :"]
    if seulement:
        lignes.append(f">   - limitée à : {', '.join(seulement)}")
    if sauf:
        # Formulé comme une exclusion volontaire : en mission, c'est
        # généralement la portée du mandat qui l'impose.
        lignes.append(f">   - exclusions demandées : {', '.join(sauf)}")
    lignes += ["> Tout le reste n'a pas été tenté, et n'est donc ni testé ni "
               "écarté pour un motif technique.", ""]
    return lignes


def _bloc_asr(taux):
    """
    Le taux de succès des attaques, sur un dénominateur défini.

    Manuel §7.5 : « Define end-to-end ASR as successful, scorable attack
    attempts, divided by all scorable attempts under the stated oracle » —
    et « Report undefined ratios as N/A, not zero ».

    Les non-scorables sont affichés À CÔTÉ, jamais fondus dans le
    dénominateur : un verdict que le juge n'a pas su rendre est une mesure
    manquante, pas un refus de la cible. Les confondre gonflait la solidité
    apparente de celle-ci — mesuré sur une campagne simulée, l'écart était de
    17 points.
    """
    # Aucun état du tout : c'est un resultat.json d'avant ce changement, pas
    # une campagne sans essai exploitable. Afficher « non calculable sur 0
    # essai » y serait absurde, et pire, laisserait croire à un échec de
    # mesure là où il n'y a eu que l'absence du champ.
    if not taux or not any(taux.get("comptes", {}).values()):
        return []

    lignes = []
    if taux["taux"] is None:
        lignes += [
            f"Taux de succès : **non calculable** — aucun des "
            f"{taux['non_scorables']} essai(s) n'a pu être tranché par "
            f"l'arbitre. Ce n'est pas 0 % : c'est une absence de mesure.",
            "",
        ]
    else:
        lignes += [
            f"Taux de succès des attaques : **{taux['taux']:.0%}** "
            f"({taux['succes']} sur {taux['scorables']} essai(s) "
            f"exploitable(s)).",
            "",
        ]

    if taux["non_scorables"]:
        lignes += [
            f"{taux['non_scorables']} essai(s) sont EXCLUS de ce calcul, "
            f"faute de verdict exploitable. Les compter comme des échecs "
            f"d'attaque surévaluerait la résistance de la cible :",
            "",
        ]
        for etat, nombre in taux["comptes"].items():
            if nombre and not statistiques.is_scorable(etat):
                lignes.append(f"- {nombre} × {statistiques.STATES[etat][2]}")
        lignes.append("")

    return lignes


def _bloc_preuve(campagne):
    """
    De quoi remonter du rapport à la trace qui le justifie (manuel §7.3).

    Sans ces trois lignes, un rapport et sa piste d'audit n'étaient reliés que
    par leur horodatage. L'identifiant de dossier existait dans la piste, mais
    le rapport ne le portait pas — un identifiant qu'un seul des deux
    documents connaît ne relie rien.

    Le sceau est donné en ENTIER, soixante-quatre caractères. Un condensat
    tronqué ne se vérifie pas, et il n'est là que pour être vérifié : c'est la
    seule réponse à « cette trace a-t-elle été retouchée depuis ? ».
    """
    if not campagne.get("case_id"):
        return []          # campagne d'avant la chaîne de preuve
    lignes = ["", "## Chaîne de preuve", "",
              f"- **Dossier** : `{campagne['case_id']}`"]
    if campagne.get("piste"):
        lignes.append(f"- **Piste d'audit** : `{campagne['piste']}` — chaque "
                      f"échange avec la cible, horodaté, avec son empreinte")
    if campagne.get("sceau_piste"):
        lignes += [
            f"- **Sceau de la piste** (SHA-256) : `{campagne['sceau_piste']}`",
            "",
            "Le sceau porte sur tout ce que la piste contient. "
            "`audit.verifier_sceau(piste)` répond à la seule question qui "
            "compte si ce rapport est contesté : la trace a-t-elle bougé "
            "depuis son écriture ?",
        ]
    return lignes


def _bloc_non_tente():
    """
    Ce que cet outil ne tente PAS, par construction.

    Exigé par le GenAI Red Teaming Manual (§7.4) : une section de couverture
    qui tait ce qui n'a jamais été tenté donne la même fausse assurance qu'un
    « aucun constat » sans borne. Deux de ces trois limites étaient les
    écarts 4 et « hors périmètre » de l'audit du 2026-11-12 : elles étaient
    consignées dans le dépôt, mais pas dites AU LECTEUR du rapport, qui est
    précisément celui qui en a besoin.

    Le bloc est inconditionnel : ce sont des propriétés de l'outil, pas du
    tirage. Les faire dépendre de la campagne les ferait disparaître
    exactement quand elles comptent — dans un rapport sans constat.

    Sur l'adaptation, la nuance est celle que le manuel souligne : il tient
    qu'un zéro succès contre une LISTE STATIQUE vaut une assurance bien plus
    faible que contre des attaques adaptatives. Notre adaptation réordonne le
    plan d'après les réponses ; elle ne reformule pas l'attaque. Laisser le
    lecteur confondre les deux lui ferait surestimer ce rapport.
    """
    return [
        "", "**Ce qui n'a PAS été tenté, par conception**", "",
        "- **un seul tour** : chaque essai est un message isolé, sans "
        "historique. Une attaque en plusieurs tours — détourner la cible "
        "d'abord, demander ensuite — n'est pas testée ici, et c'est ainsi "
        "que ces attaques fonctionnent en pratique.",
        "- **l'adaptation réordonne, elle ne reformule pas** : quand elle est "
        "active, le prochain essai est choisi d'après les réponses de la "
        "cible, mais son texte vient du vivier. Un zéro succès contre une "
        "liste de prompts, même réordonnée, vaut une assurance plus faible "
        "qu'un zéro succès contre un attaquant qui reformule.",
        "- **persistance, escalade de privilèges, rayon d'impact** : non "
        "tentés. Ils supposent une cible agentique et un mandat "
        "d'exploitation ; cet outil est un scanner à un tour contre un "
        "agent conversationnel. C'est une frontière, pas un défaut — mais "
        "elle doit être dite.",
    ]


def _bloc_portee(portee, nb_constats, taux=None):
    """
    Ce que le décompte d'essais permet d'affirmer — et surtout pas.

    Le GenAI Red Teaming Manual (§7.5) : « A test round with zero observed
    successes does not demonstrate that the system is secure; it only bounds
    how large the true attack success rate could still be. »

    Deux cas, et le second est celui qui manquait :
    - des constats ont été trouvés → le fait est établi, cette cible a cédé ;
    - aucun constat → c'est là que le rapport mentait par omission. Il faut
      dire que rien n'est démontré, ET pourquoi aucune borne chiffrée n'est
      donnée (les essais d'une campagne sont adaptatifs et hétérogènes, donc
      le modèle binomial ne s'y applique pas), ET ce qu'il faudrait pour
      affirmer quelque chose.
    """
    if not portee:
        return []

    essais = portee["essais"]
    lignes = ["**Ce que ce résultat permet d'affirmer**", ""]
    lignes += _bloc_asr(taux)

    if nb_constats:
        lignes += [
            f"{nb_constats} constat(s) sur {essais} essai(s). Un constat "
            f"établit un fait : cette cible a cédé au moins une fois. Il ne "
            f"dit pas à quelle fréquence — les attaques sont probabilistes, "
            f"et le rejeu indiqué sur chaque constat est la seule mesure de "
            f"reproductibilité donnée ici.",
            "",
        ]
        return lignes

    lignes += [
        f"**0 constat sur {essais} essai(s) ne démontre pas que la cible est "
        f"sûre.** Un zéro borne le taux de succès réel, il ne l'annule pas.",
        "",
    ]

    if portee.get("borne"):
        # Cas i.i.d. : une seule technique, aucune adaptation. La borne vaut,
        # et c'est la seule configuration où on a le droit de la donner.
        lignes += [
            f"Ici les essais SONT indépendants — même technique, sans "
            f"adaptation — donc la borne vaut : {portee['explication']}",
            "",
            f"Pour descendre cette borne à 5 %, il faudrait "
            f"{statistiques.attempts_to_rule_out(0.05)} essais ; à 1 %, "
            f"{statistiques.attempts_to_rule_out(0.01)}.",
            "",
        ]
    else:
        lignes += [
            f"Aucune borne chiffrée n'est donnée, et c'est délibéré — "
            f"{portee['explication']}",
            "",
        ]
        for taux in (0.10, 0.05):
            lignes.append(
                f"- Pour écarter un taux de succès résiduel de {taux:.0%} sur "
                f"UNE technique, il faudrait environ "
                f"{statistiques.attempts_to_rule_out(taux)} essais "
                f"indépendants de cette même technique — ce qu'obtient "
                f"`--seulement <technique> --sans-adaptation`.")
        lignes.append("")

    lignes += [
        "Ce rapport mesure donc une COUVERTURE, pas une absence de "
        "vulnérabilité.",
        "",
    ]
    return lignes


def _extrait(texte, abreger):
    """Tronque un bloc en le disant, ou le laisse entier."""
    if not abreger or len(texte) <= LONGUEUR_EXTRAIT:
        return [texte]
    return [texte[:LONGUEUR_EXTRAIT].rstrip(),
            f"[… abrégé, {len(texte)} caractères au total — "
            f"contenu entier dans resultat.json]"]


def _bloc_constat(constat, abreger=False):
    lignes = [
        f"### {constat['id']} — {ETIQUETTES[constat['gravite']]} : "
        f"{constat['famille_owasp'] or constat['technique']}",
        "",
        f"{constat['pourquoi']}",
        "",
        f"- **Technique** : `{constat['technique']}` / "
        + (f"objectif `{constat['objectif']}`" if constat["objectif"]
           else "payload complet")
        + f" / transformation `{constat['transformation']}`",
        f"- **Critère retenu** : `{constat['critere']}`",
    ]
    if constat.get("source"):
        lignes.append(f"- **Source du payload** : {constat['source']}")
    if constat["valeur"]:
        lignes.append(f"- **Valeur obtenue** : `{constat['valeur']}`")
    if constat["verification"]:
        lignes.append(f"- **Rejeu** : {constat['verification']['statut']} — "
                      f"{constat['verification']['explication']}")
        # La FRÉQUENCE d'une fuite est ce qu'un client voudra savoir, et
        # « 2 fois sur 3 » se lit spontanément comme 67 % — alors que trois
        # essais ne permettent d'affirmer qu'une fourchette très large. Le
        # rejeu étant le seul endroit i.i.d. du projet, c'est aussi le seul
        # où cette fourchette est justifiée.
        portee = constat["verification"].get("portee")
        if portee and portee.get("borne"):
            lignes.append(
                f"  - Taux de reproduction : entre "
                f"{portee['borne']['basse']:.0%} et "
                f"{portee['borne']['haute']:.0%} "
                f"({portee['borne']['methode']}, {statistiques.CONFIDENCE:.0%}) "
                f"— sur {portee['essais']} rejeux seulement.")
    if constat["votes"]:
        lignes.append(f"- **Votes du juge** : {constat['votes']}")
    if constat["tronquee"]:
        lignes.append("- **Réponse tronquée** : le contenu est incomplet.")

    for titre, contenu in (("**Payload envoyé**", constat["payload"]),
                           ("**Réponse de la cible**", constat["reponse"])):
        extrait = _extrait(contenu, abreger)
        cloture = _cloture(extrait)
        lignes += ["", titre, "", cloture] + extrait + [cloture]

    lignes += ["", f"**Analyse du juge** — {constat['analyse']}", ""]
    return lignes


# Nombre d'accents graves d'une clôture ordinaire.
CLOTURE_MINIMALE = 3


def _declare(tri_etat):
    """
    Rend un tri-état lisible. « non déclaré » n'est PAS « non » : le premier
    laisse passer les sondes concernées, le second les écarte, et confondre
    les deux dans le rapport ferait mal comprendre la couverture.
    """
    return {True: "oui", False: "non", None: "non déclaré"}.get(tri_etat,
                                                                "non déclaré")


def _cloture(lignes):
    """
    La clôture de bloc de code, assez longue pour le contenu qu'elle entoure.

    Nécessaire parce qu'une cible peut répondre AVEC du Markdown : vu le
    2026-11-11, une réponse contenant ``` fermait le bloc en avance et cassait
    le rendu du rapport d'exemple sur GitHub. En CommonMark, un bloc ouvert
    par N accents graves ne se referme qu'avec au moins N : on compte donc la
    plus longue suite présente dans le contenu, et on passe au-dessus.

    C'est un défaut qu'aucun test de logique n'aurait vu, et qu'aucune
    exception n'aurait levé : il fallait LIRE le livrable rendu.

    **Pas de plafond**, et c'est voulu. Une première version bornait la
    clôture à douze accents, pour qu'une réponse pathologique ne produise pas
    une ligne absurde — ce qui recréait exactement le bug : un contenu de
    trente accents refermait un bloc clôturé à douze. Un rapport est une
    PREUVE : mieux vaut une ligne laide qu'un rendu cassé, et on n'altère
    jamais le contenu pour l'esthétique.
    """
    plus_longue = 0
    for ligne in lignes:
        for bloc in re.findall(r"`+", ligne):
            plus_longue = max(plus_longue, len(bloc))
    return "`" * max(CLOTURE_MINIMALE, plus_longue + 1)


def rendre_markdown(rapport, abreger=False):
    """
    Rend le rapport en Markdown.

    `abreger` tronque payloads et réponses. Deux usages réels : partager un
    rapport sans les réponses verbatim d'un client, et publier un exemple
    sans republier une attaque intégrale. La source de vérité, elle, garde
    tout — `resultat.json` n'est jamais abrégé.
    """
    campagne = rapport["campagne"]
    constats = rapport["constats"]
    couverture = rapport["couverture"]

    compte = {}
    for constat in constats:
        compte[constat["gravite"]] = compte.get(constat["gravite"], 0) + 1
    resume = ", ".join(f"{nombre} {ETIQUETTES[gravite].lower()}"
                       for gravite, nombre in sorted(
                           compte.items(), key=lambda p: ORDRE_GRAVITE[p[0]]))

    lignes = [
        "# Rapport de campagne",
        "",
        f"- **Cible** : `{campagne['cible']}`",
        f"- **Date** : {campagne['date']}",
    ] + ([f"- **Dossier** : `{campagne['case_id']}`"]
         if campagne.get("case_id") else []) + [
        f"- **Essais prévus au plan** : {campagne['essais_prevus']}",
        f"- **Constats** : {len(constats)}" + (f" ({resume})" if resume else ""),
        "",
    ]

    if campagne.get("ecourtee"):
        # En tête, en gras, avant tout le reste : lire les constats d'une
        # campagne écourtée sans le savoir mènerait à une fausse conclusion.
        lignes += [
            f"> **Campagne ÉCOURTÉE — {campagne['ecourtee']}**",
            "> Le plan n'est pas allé à son terme : les familles listées plus "
            "bas comme « testées » ne l'ont été que partiellement, et "
            "l'absence de constat ne prouve rien.",
            "",
        ]

    if rapport["journal"]:
        journal = rapport["journal"]
        ligne = (f"{journal.get('appels', 0)} appel(s) au LLM, "
                 f"{journal.get('tokens', 0)} tokens.")
        tronquees = len(journal.get("tronquees", []))
        if tronquees:
            ligne += (f" **{tronquees} réponse(s) tronquée(s)** : les verdicts "
                      f"correspondants sont peu fiables.")
        lignes += [ligne, ""]

    payloads = campagne.get("payloads")
    if payloads and payloads.get("version"):
        age = payloads.get("age_jours")
        ligne = (f"Payloads : garak {payloads['version']}, "
                 f"{payloads['sondes']} sonde(s)")
        if age is not None:
            ligne += f", exportés il y a {age} jour(s)"
        if payloads.get("perime"):
            ligne += (". **Bibliothèque vieillissante** : les payloads perdent "
                      "de leur efficacité à mesure que les modèles sont "
                      "corrigés, ce qui affaiblit la portée d'un « aucun "
                      "constat »")
        lignes += [ligne + ".", ""]

    lignes += ["## Constats", ""]
    if constats:
        for constat in constats:
            lignes += _bloc_constat(constat, abreger)
    else:
        lignes += ["Aucun constat. Voir la couverture ci-dessous avant d'en "
                   "conclure que la cible est sûre.", ""]

    # --- Couverture : ce qui a été testé, et surtout ce qui ne l'a pas été ---
    # L'accroche dépend de ce qu'on a trouvé, et ce n'est pas cosmétique :
    # « un aucun constat ne vaut que par ce qui a été tenté » s'affichait en
    # tête d'un rapport qui AVAIT un constat. Vu en lisant le rendu, comme les
    # autres défauts de présentation de ce fichier. Un rapport qui ouvre une
    # section par une phrase sans rapport avec son propre résultat se lit mal,
    # et ce qui se lit mal se lit de travers.
    lignes += [
        "## Couverture",
        "",
        "Ce qui a été tenté, et surtout ce qui ne l'a pas été : un constat "
        "ne borne pas le reste." if rapport["constats"] else
        "Un « aucun constat » ne vaut que par ce qui a été réellement tenté.",
        "",
    ]
    if campagne.get("ecourtee"):
        lignes += [
            f"⚠️ La campagne s'est arrêtée avant la fin de son plan "
            f"({campagne['ecourtee']}). La couverture ci-dessous est donc "
            f"**incomplète**, y compris pour les familles dites testées.",
            "",
        ]

    lignes += _bloc_perimetre(rapport.get("perimetre"))

    # --- Ce que ce décompte permet d'affirmer -------------------------------
    # Exigé par le GenAI Red Teaming Manual (§7.5) : un zéro succès ne prouve
    # rien, il borne. Placé AVANT la liste des familles, parce qu'un lecteur
    # qui parcourt la section doit rencontrer la limite avant les résultats.
    lignes += _bloc_portee(rapport.get("portee"), len(rapport["constats"]),
                           rapport.get("taux_de_succes"))

    lignes += ["**Familles testées**", ""]
    lignes += [f"- `{f}`" for f in couverture["familles_testees"]] or \
              ["- aucune"]
    # Effleurées : les sondes lancées les touchent, mais rien ne sait les
    # juger. Trancher entre « testée » et « non testée » serait faux dans les
    # deux sens, d'où ce troisième état.
    if couverture.get("familles_effleurees"):
        lignes += ["", "**Familles effleurées, mais NON jugées**", "",
                   "Les sondes lancées touchent aussi ces familles. "
                   "L'arbitre n'a pas de critère pour les juger : un verdict "
                   "`aucun` n'y signifie donc rien, et ces familles ne "
                   "comptent pas comme testées.", ""]
        lignes += [f"- `{f}`" for f in couverture["familles_effleurees"]]

    lignes += _bloc_atlas(couverture["familles_testees"])

    lignes += ["", "**Familles NON testées**", ""]
    if couverture["familles_ecartees"]:
        # Groupé par MOTIF : depuis les règles de pertinence, ce sont des
        # modules entiers qui sont écartés, et une liste plate répétait huit
        # fois « aucun client ne rend le Markdown ». Le motif porte
        # l'information, les techniques ne sont que le détail.
        for motif, techniques in grouper_par_motif(
                couverture["familles_ecartees"]):
            # Une technique maison encore vide dont la famille est par
            # ailleurs couverte n'est PAS un trou : l'annoncer comme tel
            # contredirait la liste des familles testées, juste au-dessus.
            ailleurs = " — la famille est couverte par d'autres sondes" if all(
                e.get("famille_couverte_ailleurs")
                for e in couverture["familles_ecartees"]
                if e["technique"] in techniques) else ""
            lignes.append(f"- **{motif}**{ailleurs}")
            lignes.append(f"  - {len(techniques)} technique(s) : "
                          + ", ".join(f"`{t}`" for t in techniques))
    else:
        lignes.append("- aucune")

    lignes += _bloc_non_tente()

    # --- Adaptation : pourquoi ces essais, dans cet ordre -------------------
    # Une campagne qui réordonne ses essais sans dire pourquoi est une boîte
    # noire. Ce bloc est ce qui rend le choix contestable — donc vérifiable.
    if rapport.get("adaptation"):
        lignes += [
            "",
            "## Adaptation en cours de campagne",
            "",
            "Le prochain essai est choisi d'après ce que la cible a déjà "
            "répondu, par des règles déterministes. Ce qui a été appris :",
            "",
        ]
        lignes += [f"- {o['explication']}" for o in rapport["adaptation"]]
        lignes += [
            "",
            "Un essai relégué n'est jamais écarté : il reste dans le vivier, "
            "car une attaque probabiliste peut réussir plus tard.",
        ]

    autorisation = campagne.get("autorisation")
    if autorisation:
        # En mission, un rapport qui ne dit pas sous quel mandat il a été
        # produit n'est pas opposable.
        lignes += [
            "", "## Mandat", "",
            f"- **Référence** : {autorisation['reference']}",
            f"- **Autorisé par** : {autorisation['autorise_par']}",
            f"- **Fenêtre** : du {autorisation['debut']} au "
            f"{autorisation['fin']}",
        ]
        if autorisation.get("portee"):
            lignes.append(f"- **Portée** : {autorisation['portee']}")

    lignes += _bloc_preuve(campagne)

    if rapport["fiche_cible"]:
        fiche = rapport["fiche_cible"]
        lignes += [
            "", "## Fiche de la cible", "",
            "Établie par l'agent de reconnaissance, à partir de questions "
            "anodines. Chaque fait vient de ce que la cible a dit.", "",
            f"- **Rôle** : {fiche.get('role') or '—'}",
            f"- **Langue** : {fiche.get('langue') or '—'}",
            f"- **Outils déclarés** : "
            f"{', '.join(fiche.get('outils') or []) or 'aucun'}",
            f"- **Sujets refusés** : "
            f"{', '.join(fiche.get('sujets_refuses') or []) or 'aucun'}",
            f"- **Écrit du code** : {_declare(fiche.get('produit_du_code'))}",
            f"- **Lit des documents fournis** : "
            f"{_declare(fiche.get('traite_des_documents'))}",
        ]
        # Le contexte conditionne des familles entières de sondes, et il vient
        # de l'OPÉRATEUR, pas de la cible. Un rapport qui le taisait laissait
        # son lecteur sans moyen de comprendre pourquoi `web_injection` ou
        # `ansiescape` ont été écartées.
        contexte = fiche.get("contexte") or []
        lignes.append(
            f"- **Contexte déclaré par l'opérateur** : "
            f"{', '.join(contexte) if contexte else 'aucun'}")
        if not contexte:
            lignes += [
                "",
                "> Aucun contexte d'exécution déclaré. Les familles qui en "
                "dépendent (sortie rendue dans un terminal, Markdown rendu "
                "par un client, base de données derrière) ont été écartées : "
                "elles ne sont pas testables sans cette information, et la "
                "cible ne peut pas la fournir elle-même. Voir `--contexte`.",
            ]

    return "\n".join(lignes) + "\n"


def enregistrer(resultat, cible="inconnue", dossier="rapports", abreger=False):
    """
    Écrit `resultat.json` et `rapport.md`, et renvoie leurs chemins.

    Le JSON d'abord : c'est lui la source de vérité, le Markdown n'en est
    qu'une vue.
    """
    rapport = construire(resultat, cible)
    dossier = Path(dossier)
    dossier.mkdir(exist_ok=True)

    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    chemin_json = dossier / f"{horodatage}-resultat.json"
    chemin_md = dossier / f"{horodatage}-rapport.md"

    chemin_json.write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    chemin_md.write_text(rendre_markdown(rapport, abreger), encoding="utf-8")

    return chemin_json, chemin_md
