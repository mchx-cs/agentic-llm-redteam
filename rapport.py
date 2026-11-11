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
        "constats": constats,
        "journal": resultat.get("journal", {}),
    }


# --- Rendu Markdown ----------------------------------------------------------

# Longueur d'un extrait abrégé. Assez pour reconnaître le payload et juger
# du contexte, trop court pour republier une attaque ou les réponses
# verbatim d'un client.
LONGUEUR_EXTRAIT = 300


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
    lignes += [
        "## Couverture",
        "",
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

    lignes += ["", "**Familles NON testées**", ""]
    if couverture["familles_ecartees"]:
        for ecartee in couverture["familles_ecartees"]:
            # La technique d'abord : deux d'entre elles peuvent relever de la
            # même famille OWASP, et n'afficher que la famille donnerait deux
            # lignes identiques sans dire laquelle a été écartée.
            famille = (f" ({ecartee['famille_owasp']})"
                       if ecartee["famille_owasp"] else "")
            # Une technique maison encore vide dont la famille est par
            # ailleurs couverte n'est PAS un trou : l'annoncer comme tel
            # contredirait la liste des familles testées, juste au-dessus.
            ailleurs = (" — la famille est couverte par d'autres sondes"
                        if ecartee.get("famille_couverte_ailleurs") else "")
            lignes.append(f"- `{ecartee['technique']}`{famille} — "
                          f"{' ; '.join(ecartee['motifs'])}{ailleurs}")
    else:
        lignes.append("- aucune")

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
