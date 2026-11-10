"""
payloads/exporter_garak.py — Exporte les sondes de garak en instantané local.

**Ce script ne tourne PAS dans le venv du projet.** Il s'exécute avec un
environnement où garak est installé, et n'importe rien du projet : c'est sa
seule dépendance au reste, et c'est voulu. Les 164 paquets de garak
(`torch`, `transformers`, `langchain`…) restent ainsi dans un venv jetable,
jamais dans celui du projet, jamais sur le chemin d'une campagne.

    python -m venv /tmp/venv-garak
    /tmp/venv-garak/bin/pip install garak
    /tmp/venv-garak/bin/python payloads/exporter_garak.py

Le modèle est celui de nuclei : l'outil reste léger, les payloads sont une
bibliothèque séparée, maintenue en amont, qu'on synchronise par une commande
explicite. Une campagne lit un instantané LOCAL — aucun réseau, aucune
latence, et deux campagnes identiques envoient les mêmes payloads.

Ce qu'il faut savoir avant de lancer :
- **Charger les sondes télécharge des jeux de données tiers** (JailbreakBench
  depuis HuggingFace, images FigStep…), avec leurs propres licences. C'est
  pourquoi l'instantané produit reste HORS GIT : on pointe vers la source,
  on ne la republie pas depuis un dépôt personnel.
- Le premier export est long (plusieurs minutes) et occupe quelques
  gigaoctets de cache HuggingFace.
- garak est sous Apache-2.0 (NVIDIA). L'instantané enregistre sa version,
  pour qu'une campagne reste rattachable à une version précise de la source.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Ce que ce projet sait juger : détournement d'instructions et fuite
# d'information. Les autres familles seraient importées pour rien —
# l'arbitre n'a que les critères `divulgation` et `obeissance`, et
# répondrait `aucun` à tout le reste.
FAMILLES_RETENUES = {"owasp:llm01", "owasp:llm02", "owasp:llm07"}

# Hors périmètre, quel que soit le tag. Ces sondes mesurent la modération du
# modèle, pas sa résistance à l'injection. `ContinueSlursReclaimedSlurs` est
# par exemple tagguée llm01 et active par défaut, mais son objectif déclaré
# est de faire produire une insulte ethnique.
# Liste tenue à partir des objectifs RÉELLEMENT déclarés par garak, corrigée
# à chaque export : « forbidden » a été ajouté après avoir vu passer
# adaptive_attacks.AdaptiveAttacks (« produce a forbidden response »), dont
# les payloads demandent des instructions dangereuses.
MOTS_HORS_SUJET = ("slur", "profanity", "toxic", "harmful", "cbrn", "ethnic",
                   "hate", "forbidden", "unsafe", "dangerous", "illegal",
                   "weapon")


def _hors_sujet(nom, objectif):
    """
    Filtre sur le nom et l'OBJECTIF DÉCLARÉ de la sonde, que garak énonce en
    une phrase claire (« disregard the system prompt », « output an ethnic
    slur »). C'est grossier, mais auditable : chaque exclusion est consignée
    avec son motif dans l'instantané, et la liste se corrige à l'usage.
    """
    texte = f"{nom} {objectif}".lower()
    return next((mot for mot in MOTS_HORS_SUJET if mot in texte), None)


def collecter(familles=None, actives_seulement=True, maximum_par_sonde=None):
    """
    Parcourt les sondes de garak et renvoie celles du périmètre.

    `actives_seulement` suit le réglage de garak lui-même : une sonde non
    active par défaut est généralement une variante exhaustive (« Full »),
    utile en audit profond, disproportionnée pour une campagne ordinaire.
    """
    import garak._plugins as plugins

    familles = familles or FAMILLES_RETENUES
    retenues, ecartees = [], []

    for nom, _ in plugins.enumerate_plugins("probes"):
        try:
            sonde = plugins.load_plugin(nom, break_on_fail=False)
        except Exception as erreur:            # une sonde cassée en amont
            ecartees.append({"nom": nom, "motif": f"chargement : {erreur}"})
            continue

        prompts = [p for p in (getattr(sonde, "prompts", None) or [])
                   if isinstance(p, str) and p.strip()]
        tags = set(getattr(sonde, "tags", []))
        objectif = (getattr(sonde, "goal", "") or "").strip()
        owasp = sorted(t for t in tags if t.startswith("owasp:"))

        if not prompts:
            continue                            # sonde générative, pas statique
        if not (tags & familles):
            continue                            # hors des familles jugeables
        if actives_seulement and not getattr(sonde, "active", False):
            ecartees.append({"nom": nom, "motif": "non active par défaut"})
            continue

        mot = _hors_sujet(nom, objectif)
        if mot:
            ecartees.append({"nom": nom,
                             "motif": f"hors périmètre (« {mot} ») : {objectif}"})
            continue

        retenues.append({
            "sonde": nom,
            "objectif": objectif,
            "familles_owasp": owasp,
            "langue": getattr(sonde, "lang", None),
            "doc": getattr(sonde, "doc_uri", "") or "",
            "payloads": prompts[:maximum_par_sonde],
            "payloads_disponibles": len(prompts),
        })

    return retenues, ecartees


def construire_instantane(retenues, ecartees):
    import garak

    return {
        "_source": "garak (NVIDIA), Apache-2.0 — "
                   "https://github.com/NVIDIA/garak",
        "_avertissement": "Instantané local, HORS GIT. Les sondes de garak "
                          "incorporent des jeux de données tiers ayant leurs "
                          "propres conditions : ne pas republier.",
        "version_garak": getattr(garak, "__version__", "inconnue"),
        "exporte_le": datetime.now().isoformat(timespec="seconds"),
        "familles_retenues": sorted(FAMILLES_RETENUES),
        "sondes": retenues,
        # On consigne ce qui a été écarté et pourquoi : même logique que le
        # plan d'une campagne, qui dit ce qu'il n'a pas testé.
        "ecartees": ecartees,
    }


def principal(arguments=None):
    parseur = argparse.ArgumentParser(
        description="Exporte les sondes de garak (à lancer dans le venv garak).")
    parseur.add_argument("--sortie", default="payloads/garak.json",
                         help="fichier d'instantané (défaut : payloads/garak.json)")
    parseur.add_argument("--toutes", action="store_true",
                         help="inclure les sondes non actives par défaut "
                              "(variantes exhaustives, bien plus volumineuses)")
    parseur.add_argument("--max-par-sonde", type=int, default=None,
                         metavar="N",
                         help="ne garder que les N premiers payloads par sonde")
    arguments = parseur.parse_args(arguments)

    try:
        import garak  # noqa: F401
    except ImportError:
        print("garak n'est pas installé dans cet environnement.\n"
              "  Ce script se lance avec le venv garak, pas celui du projet :\n"
              "    python -m venv venv-garak\n"
              "    venv-garak/Scripts/pip install garak\n"
              "    venv-garak/Scripts/python payloads/exporter_garak.py",
              file=sys.stderr)
        return 2

    # Pas d'accent ni de ponctuation Unicode dans les messages : cet
    # environnement n'est pas le notre, sa console peut etre en cp1252.
    print("Chargement des sondes (long au premier lancement : garak "
          "telecharge des jeux de donnees tiers)...", file=sys.stderr)
    retenues, ecartees = collecter(
        actives_seulement=not arguments.toutes,
        maximum_par_sonde=arguments.max_par_sonde)

    # Garde-fou : si garak réorganise son API privée (`_plugins`), la
    # collecte peut ne plus rien ramener SANS lever d'exception. Écraser
    # alors l'instantané existant priverait silencieusement les campagnes de
    # leurs payloads, et un « aucun constat » passerait pour un bon résultat.
    if not retenues:
        print("Aucune sonde retenue : l'instantane existant est CONSERVE.\n"
              f"  {len(ecartees)} sonde(s) ecartee(s). Causes probables :\n"
              "  - l'API de garak a change (ce script utilise garak._plugins,\n"
              "    qui est privee) ;\n"
              "  - les familles retenues ne correspondent plus a ses tags.",
              file=sys.stderr)
        return 1

    instantane = construire_instantane(retenues, ecartees)
    chemin = Path(arguments.sortie)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(instantane, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    total = sum(len(s["payloads"]) for s in retenues)
    print(f"{len(retenues)} sonde(s), {total} payload(s) -> {chemin}")
    print(f"{len(ecartees)} sonde(s) écartée(s) ; garak "
          f"{instantane['version_garak']}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
