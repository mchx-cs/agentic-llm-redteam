"""
payloads/source_garak.py — Inventorie la source garak (phase 7).

garak (NVIDIA, Apache-2.0) maintient une collection de sondes tenue à jour
au fil de l'évolution des modèles. Plutôt que d'écrire des payloads à la
main — qui vieillissent vite et n'engagent que nous — on s'appuie sur cette
source reconnue.

**Sans installer garak.** Le paquet tire 164 dépendances, dont `torch` et
`transformers` : plusieurs gigaoctets, qui ruineraient la promesse
d'installation légère du projet. Or ses payloads vivent dans des fichiers
JSON autonomes, qu'on peut lire directement.

**Sans rien recopier dans le dépôt non plus**, le jour où on importera.
Trois raisons :
- le dépôt est public, et republier le corpus offensif d'un tiers depuis
  un compte personnel n'est pas la même chose que d'y renvoyer ;
- l'Apache-2.0 couvre le code de garak, mais plusieurs de ces fichiers de
  données proviennent de jeux tiers dont les conditions propres n'ont pas
  été vérifiées. Pointer vers la source évite la question ;
- garak met ses sondes à jour : réimporter vaut mieux que figer une copie.

Le SHA de chaque fichier est donné par l'inventaire : une campagne restera
rattachable à une version précise de la source.

**CE QUE CE MODULE FAIT AUJOURD'HUI : il inventorie, il n'importe pas.**
L'inventaire a invalidé l'hypothèse de départ. Les fichiers de
`garak/data/payloads/` ne sont pas des attaques, ce sont des INGRÉDIENTS que
les sondes assemblent : `encoded.json` contient 2 chaînes à forte perplexité,
`domains_latentinjection.json` 3 noms de domaine d'exemple,
`normal_instructions.json` 5 demandes anodines. Les gabarits d'attaque, eux,
vivent dans le code Python des sondes (`garak/probes/*.py`), donc derrière les
164 dépendances.

Conséquence : importer ces JSON ne donnerait aucune technique d'attaque. Reste
utile ici — `normal_instructions.json` et `text_en.json` enrichiraient la
technique `controle`, et `garak/data/tags.misp.tsv` fournit le vocabulaire
OWASP (`owasp:llm01` … `owasp:llm10`) pour la correspondance des familles.

    python -m payloads.source_garak --lister
    python -m payloads.source_garak --decrire encoded.json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEPOT = "NVIDIA/garak"
CHEMIN_PAYLOADS = "garak/data/payloads"
LICENCE_SOURCE = "garak (NVIDIA), Apache-2.0 — https://github.com/NVIDIA/garak"

# Ce que ce projet teste : détournement d'instructions et fuite
# d'information. Les fichiers de garak qui relèvent d'un tout autre sujet
# (contenu nuisible, insultes) ne sont pas proposés par défaut : ils
# mesureraient la modération du modèle, pas sa résistance à l'injection,
# et l'arbitre n'a de toute façon aucun critère pour les juger.
HORS_SUJET = {
    "harmful_behaviors.json": "contenu nuisible — mesure la modération, "
                              "pas l'injection ; aucun critère chez l'arbitre",
    "slur_terms_en.json": "insultes — hors du périmètre du projet",
    "rude_french.json": "insultes — hors du périmètre du projet",
    "rude_chinese.json": "insultes — hors du périmètre du projet",
}


def _recuperer(url, delai=30):
    requete = urllib.request.Request(
        url, headers={"User-Agent": "agentic-llm-redteam (importeur garak)"})
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            return reponse.read().decode("utf-8")
    except urllib.error.HTTPError as erreur:
        raise RuntimeError(
            f"{url} : erreur HTTP {erreur.code}. Le dépôt garak a-t-il changé "
            f"de structure ?") from erreur
    except urllib.error.URLError as erreur:
        raise RuntimeError(
            f"{url} : injoignable ({erreur.reason}). Vérifie ta connexion."
        ) from erreur


def derniere_version(delai=10):
    """
    Dernière version publiée de garak, ou None si l'appel échoue.

    Un seul appel à l'API GitHub, aucun téléchargement : on DÉTECTE qu'une
    mise à jour existe, on ne la fait pas. La mise à jour reste un acte
    délibéré — elle change les payloads envoyés, et une campagne doit rester
    reproductible. C'est la même règle que `nuclei -update-templates`.

    Ne lève jamais : un réseau indisponible ne doit pas gêner une campagne.
    """
    try:
        donnees = json.loads(_recuperer(
            f"https://api.github.com/repos/{DEPOT}/releases/latest", delai))
        return donnees.get("tag_name", "").lstrip("v") or None
    except Exception:
        return None


def comparer_a_l_instantane(version_locale, delai=10):
    """
    Renvoie (version_distante, en_retard) — ou (None, False) si on ne sait pas.

    Dire « une version plus récente existe » vaut mieux qu'un compteur de
    jours : garak publie tous les 37 jours en médiane, mais toutes ses
    versions ne touchent pas aux sondes.
    """
    distante = derniere_version(delai)
    if not distante or not version_locale:
        return distante, False
    return distante, _rang(distante) > _rang(version_locale)


def _rang(version):
    """Version en tuple d'entiers, pour comparer 0.9.0 et 0.17.1 correctement."""
    nombres = []
    for morceau in str(version).split("."):
        chiffres = "".join(c for c in morceau if c.isdigit())
        nombres.append(int(chiffres) if chiffres else 0)
    return tuple(nombres)


def lister(ref="main"):
    """Inventorie les fichiers de payloads disponibles, avec leur SHA."""
    contenu = json.loads(_recuperer(
        f"https://api.github.com/repos/{DEPOT}/contents/{CHEMIN_PAYLOADS}"
        f"?ref={ref}"))
    return sorted(
        ({"nom": e["name"], "taille": e["size"], "sha": e["sha"]}
         for e in contenu
         if e["type"] == "file" and e["name"].endswith(".json")),
        key=lambda e: e["nom"])


def decrire(nom, ref="main"):
    """Lit les MÉTADONNÉES d'un fichier de payloads, et compte ses entrées."""
    donnees = json.loads(_recuperer(
        f"https://raw.githubusercontent.com/{DEPOT}/{ref}/{CHEMIN_PAYLOADS}/{nom}"))
    return {
        "nom": nom,
        "intitule": donnees.get("garak_payload_name", ""),
        "types": donnees.get("payload_types", []),
        "langue": donnees.get("lang", ""),
        "intention": donnees.get("intent"),
        "nombre": len(donnees.get("payloads", [])),
        # Les commentaires de garak catégorisent souvent les payloads : ils
        # disent de quoi il s'agit sans qu'on ait à afficher le contenu.
        "categories": sorted({c.lstrip("# ").strip()
                              for c in donnees.get("_payload_comments", [])
                              if c.strip().startswith("#")}),
    }


def _prefixe(famille):
    """`LLM07` depuis « LLM07:2025 System Prompt Leakage »."""
    return (famille or "").split(":")[0].strip()


def techniques_redondantes(bibliotheque):
    """
    Les techniques ÉCRITES À LA MAIN dont garak couvre désormais la famille.

    Pourquoi ce garde-fou. Deux techniques du dépôt existent uniquement parce
    que garak ne fournissait aucune sonde pour leur famille : les onze
    payloads LLM07 (vérifié le 2026-11-11) et les quatre payloads LLM06
    (vérifié le 2026-11-12). Or des payloads écrits à la main pourrissent —
    un jailbreak de 2026 échoue en 2027 — et leur entretien retombe sur une
    seule personne, ce qui est exactement l'argument qui a fait choisir garak
    comme source synchronisée. Le jour où une sonde garak porte LLM06 ou
    LLM07 en famille PRINCIPALE, le maison devient une dette à relire.

    Rien n'est retiré automatiquement : la machine détecte et signale,
    l'humain décide et relit. C'est le principe déjà retenu pour la
    resynchronisation elle-même, et il vaut d'autant plus ici — quatre
    registres écrits pour une cible précise peuvent rester meilleurs qu'une
    sonde générique qui porte le bon tag.

    On ne regarde que les familles PRINCIPALES, jamais les secondaires : dix
    sondes portent `owasp:llm06` en secondaire, et elles visent l'application
    autour du modèle (exfiltration par URI Markdown, XSS, injection Jinja ou
    SQL), pas l'appel d'outil. Les compter ici annoncerait un trou comblé
    qui ne l'est pas.
    """
    familles_garak = {_prefixe(technique.get("famille_owasp"))
                      for technique in bibliotheque["techniques"]
                      if technique.get("source")}
    familles_garak.discard("")

    redondantes = []
    for technique in bibliotheque["techniques"]:
        if technique.get("source"):
            continue           # une sonde garak n'est pas une dette maison
        famille = _prefixe(technique.get("famille_owasp"))
        # Sans payload, il n'y a rien à retirer : `divulgation-information`
        # est vide, donc sa redondance avec les sondes LLM02 ne coûte rien et
        # le planificateur la signale déjà. Et `controle`, qui n'a pas de
        # famille, n'est jamais redondant : c'est le témoin anodin, qu'aucune
        # sonde offensive ne remplace.
        nombre = (len(technique.get("modeles") or [])
                  + len(technique.get("payloads_complets") or []))
        if famille and nombre and famille in familles_garak:
            redondantes.append({
                "id": technique["id"],
                "famille": famille,
                "payloads": nombre,
                "sondes": sum(1 for autre in bibliotheque["techniques"]
                              if autre.get("source")
                              and _prefixe(autre.get("famille_owasp")) == famille),
            })
    return redondantes


def _signaler_redondances(bibliotheque):
    """Ce que `--version` dit des techniques maison, à jour ou non."""
    redondantes = techniques_redondantes(bibliotheque)
    if not redondantes:
        return
    print("\nDes techniques écrites à la main sont peut-être devenues "
          "redondantes :")
    for technique in redondantes:
        print(f"  {technique['id']} ({technique['payloads']} payload(s) "
              f"maison) — {technique['sondes']} sonde(s) garak portent "
              f"maintenant {technique['famille']} en famille principale.")
    print("  Relis ces sondes avant de retirer quoi que ce soit : un tag "
          "n'est pas une mesure.")


def principal(arguments=None):
    parseur = argparse.ArgumentParser(
        description="Inventorie les payloads de garak, sans installer garak.")
    parseur.add_argument("--lister", action="store_true",
                         help="inventorier les fichiers disponibles")
    parseur.add_argument("--decrire", metavar="FICHIER",
                         help="métadonnées d'un fichier (sans son contenu)")
    parseur.add_argument("--ref", default="main",
                         help="branche ou tag de garak (défaut : main)")
    parseur.add_argument("--version", action="store_true",
                         help="comparer la version de l'instantané local à la "
                              "dernière publiée (aucun téléchargement)")
    arguments = parseur.parse_args(arguments)

    if arguments.version:
        from agents.attaquant import charger_bibliotheque

        locale = (charger_bibliotheque().get("_garak") or {}).get("version")
        distante, en_retard = comparer_a_l_instantane(locale)
        print(f"instantané local : garak {locale or 'aucun'}")
        print(f"dernière publiée : garak {distante or 'inconnue (hors ligne ?)'}")
        if en_retard:
            print("\nUne version plus récente existe. Pour resynchroniser :\n"
                  "  python -m venv venv-garak\n"
                  "  venv-garak/Scripts/pip install -U garak\n"
                  "  venv-garak/Scripts/python payloads/exporter_garak.py\n"
                  "\nRelis ce que l'export retient avant de lancer une "
                  "campagne : une nouvelle version peut ajouter des sondes "
                  "hors périmètre.")
        elif distante and locale:
            print("\nL'instantané est à jour.")
        # Signalé dans les deux cas : la redondance porte sur l'instantané
        # qu'on a, pas sur le retard qu'on a pris. Une version à jour peut
        # très bien venir de combler le trou LLM06 ou LLM07.
        _signaler_redondances(charger_bibliotheque())
        return 1 if en_retard else 0

    if arguments.decrire:
        fiche = decrire(arguments.decrire, arguments.ref)
        print(f"{fiche['nom']} — {fiche['intitule']}")
        print(f"  {fiche['nombre']} payload(s), langue '{fiche['langue']}', "
              f"types {', '.join(fiche['types']) or '—'}")
        if fiche["intention"]:
            print(f"  intention : {fiche['intention']}")
        if fiche["categories"]:
            print(f"  catégories : {', '.join(fiche['categories'])}")
        return 0

    if not arguments.lister:
        parseur.print_help()
        return 1

    fichiers = lister(arguments.ref)
    print(f"{len(fichiers)} fichier(s) de payloads dans {DEPOT} "
          f"({arguments.ref}) :\n")
    for fichier in fichiers:
        marque = "  " if fichier["nom"] not in HORS_SUJET else "x "
        print(f"{marque}{fichier['nom']:<34} {fichier['taille']:>6} o")
    if any(f["nom"] in HORS_SUJET for f in fichiers):
        print("\nx = hors du périmètre de ce projet :")
        for nom, raison in HORS_SUJET.items():
            if any(f["nom"] == nom for f in fichiers):
                print(f"    {nom} : {raison}")
    print(f"\nSource : {LICENCE_SOURCE}")
    print("Détail d'un fichier : --decrire <nom>")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
