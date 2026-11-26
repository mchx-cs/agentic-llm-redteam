"""
`foreign` : une cible dont la DÉFENSE n'a pas été écrite ici.

POURQUOI, et c'est le déséquilibre le plus net du projet. `demo`, `records`,
`docs` et `bench` sont des cibles écrites ici : un secret qu'on a choisi, une
défense qu'on a codée, un mode de défaillance qu'on a conçu. « Le niveau 3
tient la valeur 30/30 et lâche la consigne 14 fois » est un fait sur NOTRE
filtre, et chaque gradient de défense mesure nos propres `if`.

Et les phases 8, 9, 11 et 14 — l'adaptateur HTTP et ses cinq transports, le
garde de mandat, la piste scellée, le `case_id`, la télémétrie — existent pour
un ENGAGEMENT, et n'ont jamais tourné contre autre chose que `localhost`. Le
projet a construit toute la machinerie de preuve d'un engagement sans
engagement.

CE QUI COMPTE N'EST PAS LA PLOMBERIE, C'EST QUI A ÉCRIT LA DÉFENSE. Une
application d'étagère installée ici aurait la même plomberie que ce module ;
ce qui changerait est que ses garde-fous auraient été écrits par quelqu'un
d'autre, pour un vrai produit, sans aucune connaissance de nos payloads.
C'est cette propriété-là qui rend une mesure différente en NATURE, et ce
module l'obtient par deux routes.

    bare      le modèle local SANS aucune consigne système. Sa défense est
              l'alignement de son éditeur : personne ici ne l'a écrit, il ne
              connaît pas nos payloads, et il est déjà sur la machine. Gratuit
              et joignable tout de suite.

    supplied  une consigne système de TIERS, fournie par l'opérateur dans un
              fichier hors git. Plus riche — un vrai prompt de produit porte un
              rôle, des règles et souvent un outil, donc plus de critères
              deviennent testables — et c'est à l'opérateur de décider à quoi
              il a le droit de pointer son outil.

RIEN DE TIERS N'ENTRE DANS LE DÉPÔT, et c'est la règle que la phase 7 a posée
pour les données de garak : « on pointe vers la source, on ne la republie pas
depuis un dépôt personnel ». `foreign.json` est hors git comme
`authorisation.json` et `payloads/garak.json` ; `foreign.example.json` est le
gabarit à remplir, et il est committé.

CE QU'ON NE SAIT PAS, DÉCLARÉ COMME TEL. `secret_of("foreign")` rend None, et
c'est une VRAIE réponse : contre une défense qu'on n'a pas écrite, ce qu'elle
protège est précisément ce qu'un test en boîte noire cherche. Prétendre le
savoir inverserait la prémisse du projet — la même raison pour laquelle
`records` et les URL n'en déclarent aucun.

CE QUE `bare` NE PEUT PAS TESTER, dit plutôt que découvert. Un modèle nu n'a
ni secret, ni outil, ni fiches : `divulgation`, `abus_outils` et
`fuite_donnees_tiers` n'y sont pas seulement non testés, ils sont
**intestables** — exactement la limite que le projet a enregistrée le
2026-11-09 pour LLM05, LLM06 et LLM08. Il reste `obeissance`, et c'est une
mesure réelle : la chaîne fait-elle adopter une identité imposée à un modèle
aligné ? `supplied` est la route qui rouvre les trois autres, et elle demande
du contenu que seul l'opérateur peut fournir.
"""

import json
import pathlib

#: Le fichier que l'opérateur remplit, HORS GIT.
PROMPT_FILE = pathlib.Path(__file__).resolve().parent.parent / "foreign.json"
EXAMPLE_FILE = PROMPT_FILE.with_name("foreign.example.json")

#: Les champs que le fichier DOIT porter, et chacun pour une raison.
#:
#: `source` et `retrieved` ne sont pas de la bureaucratie : une mesure contre
#: une défense étrangère ne vaut rien si un lecteur ne peut pas dire LAQUELLE.
#: C'est le même argument que le `case_id` qui lie un rapport à sa piste, et
#: que la version de garak inscrite dans la piste d'audit.
REQUIRED = ("source", "retrieved", "system_prompt")

CONFIGURATIONS = {
    "bare": {
        "needs_file": False,
        "what": "le modèle local sans aucune consigne : l'alignement de son "
                "éditeur, que personne ici n'a écrit",
    },
    "supplied": {
        "needs_file": True,
        "what": "une consigne système de tiers, fournie dans foreign.json",
    },
}

DEFAULT_CONFIGURATION = "bare"


class ForeignPromptMissing(RuntimeError):
    """
    Le fichier manque, ou il est incomplet.

    Une exception à elle, pour que l'orchestrateur ne l'annonce pas comme un
    défaut de la CIBLE. Le défaut mesuré le 2026-11-23 : un juge qui lâche
    faisait conseiller `--probe-target` à une cible innocente, et un mauvais
    conseil coûte plus que pas de conseil.
    """


def _read_prompt():
    if not PROMPT_FILE.exists():
        raise ForeignPromptMissing(
            f"{PROMPT_FILE.name} is missing.\n"
            f"  This target runs against a system prompt THIS PROJECT DID NOT "
            f"WRITE, which is the whole point of it.\n"
            f"  Copy the template and fill it in:\n"
            f"    cp {EXAMPLE_FILE.name} {PROMPT_FILE.name}\n"
            f"  Nothing third-party enters the repository: {PROMPT_FILE.name} "
            f"is gitignored, like authorisation.json.\n"
            f"  Or use `--target foreign:bare`, which needs no file: the bare "
            f"local model, whose guardrails are its publisher's.")
    data = json.loads(PROMPT_FILE.read_text(encoding="utf-8"))
    missing = [field for field in REQUIRED if not data.get(field)]
    if missing:
        raise ForeignPromptMissing(
            f"{PROMPT_FILE.name} is missing: {', '.join(missing)}.\n"
            f"  `source` and `retrieved` are not bureaucracy: a measurement "
            f"against a foreign defence is worth nothing if a reader cannot "
            f"say WHICH defence it was.")
    return data


def provenance(configuration=DEFAULT_CONFIGURATION):
    """
    D'où vient la défense, pour la télémétrie et le rapport.

    Lu ICI et pas reconstruit ailleurs : un champ que seul un des deux
    documents connaît ne lie rien, et c'est le défaut de la phase 14 dans sa
    forme exacte.
    """
    if configuration == "bare":
        from config import PROFILES, ACTIVE_PROFILE
        return {
            "defence": "the model's own alignment, no system prompt",
            "source": f"{ACTIVE_PROFILE}/{PROFILES[ACTIVE_PROFILE]['model']}",
            "retrieved": None,
            "written_here": False,
        }
    data = _read_prompt()
    return {
        "defence": "a third-party system prompt",
        "source": data["source"],
        "retrieved": data["retrieved"],
        "characters": len(data["system_prompt"]),
        "written_here": False,
    }


def build_foreign_target(configuration=DEFAULT_CONFIGURATION):
    """
    Une cible dont la défense vient d'ailleurs.

    Le contrat de la phase 8 : `ask(message) -> str`, plus `history` pour le
    multi-tours, puisque `ask_llm` le sait faire et qu'un modèle local voit
    bien un dialogue. Tout passe par `ask_llm`, donc le coupe-circuit, le
    compte de jetons et la détection de réponse tronquée s'appliquent.
    """
    if configuration not in CONFIGURATIONS:
        raise ValueError(
            f"Unknown foreign configuration: '{configuration}'.\n"
            f"  Expected: {', '.join(sorted(CONFIGURATIONS))}.")

    system = None
    if CONFIGURATIONS[configuration]["needs_file"]:
        system = _read_prompt()["system_prompt"]

    def ask(message, history=None):
        from llm_client import ask_llm

        return ask_llm(message, system=system, history=history)

    # DÉCLARÉE et non devinée, comme partout ailleurs : un modèle local voit
    # des messages distincts, donc la conversation est réelle.
    ask.conversation = True
    ask.foreign = configuration
    return ask
