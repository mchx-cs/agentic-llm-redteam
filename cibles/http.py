"""
cibles/http.py — Viser un vrai endpoint.

C'est l'adaptateur qui fait passer l'outil de « il se teste lui-même » à
« il vise une cible réelle ». Il parle à n'importe quelle application qui
accepte du JSON et renvoie du JSON, sans rien coder en dur : la forme de la
requête et l'endroit où lire la réponse se décrivent dans `.env`.

Pourquoi `urllib` et pas `requests` : le projet tient à sa dépendance
unique (`openai`). Un POST JSON en bibliothèque standard coûte une vingtaine
de lignes de plus, et évite une installation à qui clone le dépôt.

Rappel du cadre légal (voir CLAUDE.md) : pointer cet adaptateur vers un
système tiers sans autorisation écrite est un délit. La phase 9 rendra ce
contrôle explicite dans le code ; pour l'instant, c'est à l'opérateur.
"""

import json
import urllib.error
import urllib.request

# Jeton remplacé par le payload dans le corps de la requête.
MARQUEUR_MESSAGE = "{message}"


# --- Profils de cible : les formes qu'on rencontre en pratique ---------------
# Décrire `CIBLE_CORPS` et `CIBLE_CHEMIN_REPONSE` à la main suppose de lire la
# documentation de l'API, puis d'écrire du JSON imbriqué dans une variable
# d'environnement. C'est la partie la plus pénible du branchement, et pour le
# cas le PLUS COURANT elle est entièrement prévisible : la majorité des
# endpoints LLM parlent le dialecte OpenAI.
#
# Ces profils ne remplacent pas la configuration manuelle, ils couvrent les
# cas connus. Une application maison garde sa forme propre dans `.env`, et
# c'est bien pour ça que le projet ne devine jamais : il propose.
PROFILS_CIBLE = {
    "openai": {
        "corps": {"messages": [{"role": "user", "content": MARQUEUR_MESSAGE}]},
        "chemin_reponse": "choices.0.message.content",
        "description": "API de type OpenAI (OpenAI, Groq, Together, vLLM, "
                       "LM Studio, la plupart des passerelles)",
    },
    "ollama": {
        "corps": {"model": "llama3.2", "prompt": MARQUEUR_MESSAGE,
                  "stream": False},
        "chemin_reponse": "response",
        "description": "Ollama en direct (/api/generate), sans couche OpenAI",
    },
    "anthropic": {
        "corps": {"messages": [{"role": "user", "content": MARQUEUR_MESSAGE}],
                  "max_tokens": 1024},
        "chemin_reponse": "content.0.text",
        "description": "API Messages d'Anthropic",
    },
    "simple": {
        "corps": {"message": MARQUEUR_MESSAGE},
        "chemin_reponse": "reply",
        "description": "application maison : {\"message\": …} → {\"reply\": …}",
    },
    # Pour une application dont on ne contrôle pas le corps de la requête, et
    # qui streame sans qu'on puisse l'en empêcher — le cas d'une application
    # cliente testée sous mandat.
    "openai-flux": {
        "corps": {"messages": [{"role": "user", "content": MARQUEUR_MESSAGE}],
                  "stream": True},
        "chemin_reponse": "@flux:choices.0.delta.content",
        "description": "API de type OpenAI qui répond en flux (SSE)",
    },
    "texte": {
        "corps": {"message": MARQUEUR_MESSAGE},
        "chemin_reponse": "@brut",
        "description": "réponse en texte brut, sans JSON autour",
    },
}


def _extraire(donnees, chemin):
    """
    Suit un chemin pointé dans une réponse JSON.

    "reply" → donnees["reply"]
    "choices.0.message.content" → donnees["choices"][0]["message"]["content"]

    Les API de chatbot imbriquent toutes leur texte différemment : plutôt que
    de deviner, on laisse l'opérateur décrire le chemin.
    """
    courant = donnees
    for morceau in chemin.split("."):
        if isinstance(courant, list):
            if not morceau.isdigit():
                raise ValueError(
                    f"Chemin '{chemin}' : '{morceau}' n'est pas un indice, "
                    f"alors que la réponse contient une liste à cet endroit."
                )
            courant = courant[int(morceau)]
        elif isinstance(courant, dict):
            if morceau not in courant:
                raise ValueError(
                    f"Chemin '{chemin}' : clé '{morceau}' absente. "
                    f"Clés disponibles : {', '.join(courant) or 'aucune'}."
                )
            courant = courant[morceau]
        else:
            raise ValueError(
                f"Chemin '{chemin}' : impossible de descendre dans "
                f"'{morceau}', la valeur est un {type(courant).__name__}."
            )
    return courant


def _injecter(gabarit, message):
    """
    Place le message dans le gabarit de corps, à la place du marqueur.

    On travaille sur la structure déjà désérialisée, pas sur du texte : ainsi
    un payload contenant des guillemets ou des retours à la ligne ne casse
    pas le JSON, et ne peut pas non plus en injecter.
    """
    if isinstance(gabarit, dict):
        return {cle: _injecter(valeur, message) for cle, valeur in gabarit.items()}
    if isinstance(gabarit, list):
        return [_injecter(valeur, message) for valeur in gabarit]
    if gabarit == MARQUEUR_MESSAGE:
        return message
    return gabarit


# --- Formes de réponse autres que « un objet JSON » --------------------------
# L'adaptateur n'acceptait que du JSON, et c'est le bon défaut : travailler sur
# la structure désérialisée est ce qui rend l'injection de payload SÛRE — le
# marqueur est remplacé dans l'arbre analysé, donc un payload bourré de
# guillemets et de retours à la ligne voyage intact et ne peut rien casser.
#
# Mais deux formes se rencontrent vraiment face à un chatbot, et toutes deux
# s'obtiennent sans rien échapper à la main, puisqu'elles ne concernent QUE la
# lecture de la réponse — l'envoi reste du JSON.

# Chemin spécial : prendre le corps entier, tel qu'il est arrivé. Pour une
# application maison qui renvoie simplement la phrase du bot.
CHEMIN_TEXTE_BRUT = "@brut"

# Chemin spécial : la réponse est un flux d'événements (server-sent events).
# Le conseil « ajoute "stream": false » suppose qu'on contrôle le corps de la
# requête ; quand on teste l'APPLICATION d'un client — le cas le plus
# légitime — l'endpoint streame parfois sans qu'on puisse l'en empêcher.
CHEMIN_FLUX = "@flux:"


def _texte_du_flux(brut, chemin_interne):
    """
    Recolle les fragments d'un flux SSE en un seul texte.

    Format : des lignes « data: … », séparées par des lignes vides, et une
    sentinelle finale (`[DONE]` chez la plupart des fournisseurs). Chaque
    fragment porte un morceau de la réponse, à l'endroit décrit par
    `chemin_interne` — `choices.0.delta.content` dans le dialecte OpenAI.

    Les fragments illisibles sont IGNORÉS, pas fatals : un flux contient des
    commentaires, des pings et des événements de contrôle, et s'arrêter au
    premier perdrait la réponse entière alors qu'elle est là.
    """
    morceaux = []
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("data:"):
            continue
        charge = ligne[len("data:"):].strip()
        if not charge or charge == "[DONE]":
            continue
        try:
            fragment = _extraire(json.loads(charge), chemin_interne)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(fragment, str):
            morceaux.append(fragment)

    if not morceaux:
        raise ValueError(
            f"Flux reçu, mais aucun fragment lisible en "
            f"'{chemin_interne}'.\n"
            f"  Vérifie le chemin INTERNE après « {CHEMIN_FLUX} » : pour une "
            f"API de type OpenAI,\n"
            f"  c'est choices.0.delta.content."
        )
    return "".join(morceaux)


def lire_reponse(brut, chemin_reponse):
    """
    Extrait le texte d'une réponse, selon ce que `chemin_reponse` décrit.

    - "@brut"                      → le corps entier, sans l'analyser ;
    - "@flux:choices.0.delta.content" → un flux SSE, recollé fragment à
      fragment ;
    - "choices.0.message.content"  → un chemin pointé dans un objet JSON.

    Les deux premiers sont des cas particuliers DÉCLARÉS, jamais devinés : une
    réponse qui n'est pas du JSON reste une erreur par défaut, avec son
    diagnostic. Deviner ferait passer une page d'erreur HTML pour la réponse
    d'un chatbot, et l'arbitre jugerait du HTML.
    """
    if chemin_reponse == CHEMIN_TEXTE_BRUT:
        return brut
    if chemin_reponse.startswith(CHEMIN_FLUX):
        return _texte_du_flux(brut, chemin_reponse[len(CHEMIN_FLUX):])
    return _extraire(json.loads(brut), chemin_reponse)


def _diagnostiquer(brut):
    """
    Nomme la cause probable d'une réponse qui n'est pas du JSON.

    « JSON attendu » est exact mais ne dit pas quoi faire, et deux confusions
    reviennent sans cesse quand on branche une cible pour la première fois :
    donner l'adresse de la PAGE du chatbot au lieu de son endpoint, et viser
    une API qui répond en flux. Les deux se reconnaissent aux premiers
    caractères de la réponse, donc autant le dire.
    """
    debut = brut.lstrip()[:400].lower()

    if debut.startswith(("<!doctype", "<html", "<?xml")) or "<body" in debut:
        return ("  C'est une PAGE WEB, pas un endpoint d'API : cet outil "
                "envoie un POST JSON.\n"
                "  Il faut l'adresse que la page appelle elle-même. Pour la "
                "trouver : ouvre le\n"
                "  chatbot dans un navigateur, outils de développement "
                "(F12), onglet Réseau,\n"
                "  envoie un message, et relève l'URL de la requête POST.")

    if debut.startswith("data:") or "\ndata:" in debut:
        return ("  Cette API répond en FLUX (server-sent events).\n"
                "  Deux issues : désactiver le flux si le corps te le permet "
                '("stream": false dans\n'
                "  CIBLE_CORPS), ou lire le flux tel quel —\n"
                f"    CIBLE_CHEMIN_REPONSE={CHEMIN_FLUX}"
                "choices.0.delta.content\n"
                "    ou --profil-cible openai-flux\n"
                "  La seconde est la bonne quand tu testes l'application d'un "
                "client, qui ne\n"
                "  propose pas toujours de désactiver le flux.")

    if not debut:
        return ("  La réponse est VIDE. Vérifie que l'URL est bien celle de "
                "l'endpoint, et que\n"
                "  la méthode attendue est un POST.")

    return ("  Vérifie que cette URL est l'endpoint de l'API, et non une "
            "page ou un proxy.")


def _premier_defini(*valeurs):
    """La première valeur non-None. `{}` et `""` restent des choix valides."""
    return next((v for v in valeurs if v is not None), None)


def _contient_marqueur(gabarit):
    """Le gabarit a-t-il un emplacement où mettre le payload ?"""
    if isinstance(gabarit, dict):
        return any(_contient_marqueur(v) for v in gabarit.values())
    if isinstance(gabarit, list):
        return any(_contient_marqueur(v) for v in gabarit)
    return gabarit == MARQUEUR_MESSAGE


def verifier_gabarit(corps):
    """
    Refuse un gabarit de corps qui n'a nulle part où mettre le payload.

    LE défaut qui justifie cette fonction, et il est grave : `_injecter`
    renvoie le gabarit inchangé quand le marqueur manque. Une faute de frappe
    (`{mesage}`), un oubli, un corps recopié depuis une documentation — et la
    campagne envoie le MÊME texte fixe à chaque essai. L'arbitre répond
    « aucune faille » à chaque fois, et le rapport conclut que la cible est
    sûre.

    C'est un faux négatif silencieux, la pire erreur pour un outil de
    sécurité : rien ne lève, rien ne manque, et la conclusion est inversée.
    D'où un refus AU DÉMARRAGE plutôt qu'un contrôle à l'envoi — on ne veut
    pas découvrir ça après avoir consommé du débit sur la cible d'un client.
    """
    if _contient_marqueur(corps):
        return
    raise RuntimeError(
        f"Le gabarit du corps ne contient pas le marqueur "
        f"« {MARQUEUR_MESSAGE} » : le payload n'aurait nulle part où aller, "
        f"et la cible recevrait le même texte fixe à chaque essai.\n"
        f"  Gabarit lu : {json.dumps(corps, ensure_ascii=False)}\n"
        f"  Attendu, par exemple : "
        f'{{"message": "{MARQUEUR_MESSAGE}"}}\n'
        f"  Vérifie CIBLE_CORPS dans .env (voir .env.example)."
    )


def construire_cible_http(url, entetes=None, corps=None, chemin_reponse=None,
                          delai=None, profil=None):
    """
    Renvoie une fonction `interroger(message) -> str` qui vise `url`.

    Les paramètres non fournis sont lus dans `.env` (voir config.py) :
    - entetes        : en-têtes HTTP, dont l'authentification ;
    - corps          : gabarit JSON du corps, où "{message}" sera remplacé ;
    - chemin_reponse : où lire le texte dans la réponse JSON ;
    - delai          : secondes avant abandon ;
    - profil         : un nom de PROFILS_CIBLE, qui fournit `corps` et
                       `chemin_reponse` pour une forme d'API connue.

    Ordre de priorité : ce qui est passé explicitement, puis le profil, puis
    `.env`. Un profil est une COMMODITÉ, pas une contrainte : il ne doit
    jamais écraser un réglage posé à la main.
    """
    from config import CIBLE_HTTP

    if profil is not None and profil not in PROFILS_CIBLE:
        raise RuntimeError(
            f"Profil de cible inconnu : « {profil} ».\n"
            f"  Profils disponibles : {', '.join(PROFILS_CIBLE)}."
        )
    reglages = PROFILS_CIBLE.get(profil, {})

    entetes = {**CIBLE_HTTP["entetes"], **(entetes or {})}
    corps = _premier_defini(corps, reglages.get("corps"), CIBLE_HTTP["corps"])
    chemin_reponse = _premier_defini(
        chemin_reponse, reglages.get("chemin_reponse"),
        CIBLE_HTTP["chemin_reponse"])
    delai = delai or CIBLE_HTTP["delai"]

    # AVANT le premier appel : une campagne entière sur un gabarit muet
    # conclurait « aucune faille » sans avoir rien envoyé de ce qu'on croyait.
    verifier_gabarit(corps)

    def interroger(message):
        donnees = json.dumps(_injecter(corps, message)).encode("utf-8")
        requete = urllib.request.Request(
            url, data=donnees, method="POST",
            headers={"Content-Type": "application/json", **entetes},
        )

        try:
            with urllib.request.urlopen(requete, timeout=delai) as reponse:
                brut = reponse.read().decode("utf-8")
        except urllib.error.HTTPError as erreur:
            # Le corps d'une erreur HTTP contient souvent l'explication utile
            # (clé refusée, format invalide, quota) : on la remonte.
            detail = erreur.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Cible {url} : erreur HTTP {erreur.code}.\n  {detail}"
            ) from erreur
        except urllib.error.URLError as erreur:
            raise RuntimeError(
                f"Cible {url} : injoignable ({erreur.reason}).\n"
                f"  Vérifie l'URL, le réseau, et que la cible est démarrée."
            ) from erreur

        try:
            texte = lire_reponse(brut, chemin_reponse)
        except json.JSONDecodeError as erreur:
            raise RuntimeError(
                f"Cible {url} : réponse illisible (JSON attendu).\n"
                f"  Reçu : {brut[:200]}\n"
                f"{_diagnostiquer(brut)}"
            ) from erreur
        except ValueError as erreur:
            # Chemin de réponse mal décrit : l'erreur dit déjà quoi corriger.
            raise RuntimeError(f"Cible {url} : {erreur}") from erreur

        if not isinstance(texte, str):
            raise RuntimeError(
                f"Cible {url} : '{chemin_reponse}' donne un "
                f"{type(texte).__name__}, pas du texte."
            )
        return texte

    return interroger


# --- Vérification avant campagne ---------------------------------------------

# Ce qu'on envoie pour vérifier le branchement : anodin, et c'est voulu. Une
# vérification n'est pas une attaque — elle précède souvent le mandat, et elle
# ne doit rien laisser dans les journaux de la cible qui ressemble à un test
# d'intrusion.
MESSAGE_DE_TEST = "Bonjour, peux-tu me confirmer que tu me reçois ?"


def _chemins_plausibles(donnees, prefixe="", profondeur=4):
    """
    Les chemins pointés qui mènent à du texte, dans une réponse JSON reçue.

    C'est ce qui transforme « clé absente » en « essaie plutôt ceci » : le
    chemin correct est presque toujours dans la liste, puisqu'il mène au texte
    que la cible vient de renvoyer.
    """
    if profondeur <= 0:
        return []
    trouves = []
    if isinstance(donnees, dict):
        for cle, valeur in donnees.items():
            chemin = f"{prefixe}.{cle}" if prefixe else str(cle)
            if isinstance(valeur, str) and valeur.strip():
                trouves.append((chemin, valeur))
            else:
                trouves += _chemins_plausibles(valeur, chemin, profondeur - 1)
    elif isinstance(donnees, list):
        for indice, valeur in enumerate(donnees[:3]):
            chemin = f"{prefixe}.{indice}" if prefixe else str(indice)
            if isinstance(valeur, str) and valeur.strip():
                trouves.append((chemin, valeur))
            else:
                trouves += _chemins_plausibles(valeur, chemin, profondeur - 1)
    return trouves


def tester(url, entetes=None, corps=None, chemin_reponse=None, delai=None,
           profil=None, afficher=print):
    """
    Envoie UN message anodin et rend compte, sans rien juger.

    Pourquoi cette commande existe : les messages d'erreur du projet sont
    bons, mais ils tombaient PENDANT la campagne, après qu'un payload soit
    déjà parti. Sur la cible d'un client, sous mandat, c'est consommer du
    débit autorisé et polluer la piste d'audit pour découvrir une coquille.
    Un appel anodin en amont déplace toutes ces erreurs avant le mandat.

    Renvoie True si le branchement fonctionne. Sur un chemin de réponse
    erroné, propose les chemins qui mènent à du texte dans la réponse reçue —
    le bon y est presque toujours.
    """
    from config import CIBLE_HTTP

    reglages = PROFILS_CIBLE.get(profil, {})
    corps_final = _premier_defini(corps, reglages.get("corps"),
                                  CIBLE_HTTP["corps"])
    chemin_final = _premier_defini(chemin_reponse,
                                   reglages.get("chemin_reponse"),
                                   CIBLE_HTTP["chemin_reponse"])

    afficher(f"Cible    : {url}")
    if profil:
        afficher(f"Profil   : {profil} — {reglages['description']}")
    afficher(f"Corps    : {json.dumps(corps_final, ensure_ascii=False)}")
    afficher(f"Chemin   : {chemin_final}")
    entetes_finaux = {**CIBLE_HTTP["entetes"], **(entetes or {})}
    # On nomme les en-têtes sans montrer leur valeur : un jeton n'a rien à
    # faire dans une sortie de terminal qu'on colle dans un rapport ou un chat.
    afficher(f"En-têtes : {', '.join(entetes_finaux) or 'aucun'}"
             + (" (valeurs masquées)" if entetes_finaux else ""))
    afficher("")

    try:
        verifier_gabarit(corps_final)
    except RuntimeError as erreur:
        afficher(f"ÉCHEC — {erreur}")
        return False

    interroger = construire_cible_http(url, entetes, corps_final,
                                       chemin_final, delai, profil=None)
    afficher(f"Envoi    : {MESSAGE_DE_TEST}")
    try:
        reponse = interroger(MESSAGE_DE_TEST)
    except RuntimeError as erreur:
        afficher(f"\nÉCHEC — {erreur}")
        _suggerer(url, entetes_finaux, corps_final, delai, afficher)
        return False

    afficher(f"Réponse  : {reponse[:300]}"
             + (" […]" if len(reponse) > 300 else ""))
    afficher("\nBranchement VALIDE : la cible répond et le texte se lit bien.")
    return True


def _suggerer(url, entetes, corps, delai, afficher):
    """Relit la réponse brute pour proposer un chemin qui mène à du texte."""
    requete = urllib.request.Request(
        url, data=json.dumps(_injecter(corps, MESSAGE_DE_TEST)).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **entetes})
    try:
        with urllib.request.urlopen(requete, timeout=delai or 60) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
    except Exception:
        # La suggestion est un bonus : si elle échoue, l'erreur d'origine
        # reste affichée et c'est elle qui compte.
        return

    chemins = _chemins_plausibles(donnees)
    if not chemins:
        return
    afficher("\nChemins qui mènent à du texte dans la réponse reçue :")
    for chemin, valeur in chemins[:6]:
        extrait = valeur.replace("\n", " ")[:60]
        afficher(f"  CIBLE_CHEMIN_REPONSE={chemin}")
        afficher(f"      → {extrait!r}")

    # Si AUCUN texte reçu ne reprend ce qu'on a envoyé, c'est que la cible ne
    # l'a pas vu : le corps est faux lui aussi, et corriger le seul chemin ne
    # suffira pas. Sans cet indice, on lirait « choices.0.message.content »
    # comme la solution, on relancerait, et la cible répondrait toujours à
    # côté — en consommant du débit à chaque essai.
    extrait_envoye = MESSAGE_DE_TEST[:20]
    if not any(extrait_envoye in valeur for _, valeur in chemins):
        afficher("\nAttention : aucun de ces textes ne reprend le message "
                 "envoyé.\n  La cible ne l'a donc pas reçu là où elle "
                 "l'attendait : CIBLE_CORPS est à corriger aussi, pas "
                 "seulement le chemin.\n  Essaie --profil-cible "
                 f"{', '.join(PROFILS_CIBLE)} pour partir d'une forme connue.")
