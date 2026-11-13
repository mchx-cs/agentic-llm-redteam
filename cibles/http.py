"""
cibles/http.py — Aiming at a real endpoint.

This is the adapter that takes the tool from "it tests itself" to "it aims at a
real target". It talks to any application that accepts JSON and returns JSON,
with nothing hard-coded: the shape of the request and where to read the reply
are described in `.env`.

Why `urllib` and not `requests`: the project keeps its single dependency
(`openai`). A JSON POST in the standard library costs about twenty extra lines,
and spares an installation to whoever clones the repository.

A reminder of the legal frame (see CLAUDE.md): pointing this adapter at a
third-party system without written authorisation is an offence. `audit.py` now
makes that check explicit in code — a remote target does not start without a
mandate.

NOTE ON NAMING (2026-11-13). The `.env` keys (`CIBLE_CORPS`,
`CIBLE_CHEMIN_REPONSE`, `CIBLE_ENTETES`) and the profile dictionaries' keys
stay French: they are a CONFIGURATION contract. Renaming them would break every
existing `.env`, including those on machines this repository never sees. They
move with the coordinated data-key pass, with a documented migration. See
`GLOSSAIRE.md`.
"""

import json
import urllib.error
import urllib.request

# Token replaced by the payload inside the request body.
MESSAGE_MARKER = "{message}"


# --- Target profiles: the shapes met in practice -----------------------------
# Describing `CIBLE_CORPS` and `CIBLE_CHEMIN_REPONSE` by hand means reading the
# API's documentation, then writing nested JSON inside an environment variable.
# It is the most tedious part of wiring a target, and for the MOST COMMON case
# it is entirely predictable: most LLM endpoints speak the OpenAI dialect.
#
# These profiles do not replace manual configuration, they cover the known
# cases. A bespoke application keeps its own shape in `.env`, and that is
# precisely why the project never guesses: it offers.
TARGET_PROFILES = {
    "openai": {
        "corps": {"messages": [{"role": "user", "content": MESSAGE_MARKER}]},
        "chemin_reponse": "choices.0.message.content",
        "description": "OpenAI-style API (OpenAI, Groq, Together, vLLM, "
                       "LM Studio, most gateways)",
    },
    "ollama": {
        "corps": {"model": "llama3.2", "prompt": MESSAGE_MARKER,
                  "stream": False},
        "chemin_reponse": "response",
        "description": "Ollama directly (/api/generate), no OpenAI layer",
    },
    "anthropic": {
        "corps": {"messages": [{"role": "user", "content": MESSAGE_MARKER}],
                  "max_tokens": 1024},
        "chemin_reponse": "content.0.text",
        "description": "Anthropic's Messages API",
    },
    "simple": {
        "corps": {"message": MESSAGE_MARKER},
        "chemin_reponse": "reply",
        "description": "bespoke app: {\"message\": …} → {\"reply\": …}",
    },
    # For an application whose request body we do not control, and which
    # streams without any way to stop it — the case of a client application
    # tested under mandate.
    "openai-flux": {
        "corps": {"messages": [{"role": "user", "content": MESSAGE_MARKER}],
                  "stream": True},
        "chemin_reponse": "@flux:choices.0.delta.content",
        "description": "OpenAI-style API replying as a stream (SSE)",
    },
    "texte": {
        "corps": {"message": MESSAGE_MARKER},
        "chemin_reponse": "@brut",
        "description": "plain-text reply, no JSON around it",
    },
}


def _extract(data, path):
    """
    Follow a dotted path into a JSON reply.

    "reply" -> data["reply"]
    "choices.0.message.content" -> data["choices"][0]["message"]["content"]

    Chatbot APIs all nest their text differently: rather than guessing, we let
    the operator describe the path.
    """
    current = data
    for piece in path.split("."):
        if isinstance(current, list):
            if not piece.isdigit():
                raise ValueError(
                    f"Chemin '{path}' : '{piece}' n'est pas un indice, "
                    f"alors que la réponse contient une liste à cet endroit."
                )
            current = current[int(piece)]
        elif isinstance(current, dict):
            if piece not in current:
                raise ValueError(
                    f"Chemin '{path}' : clé '{piece}' absente. "
                    f"Clés disponibles : {', '.join(current) or 'aucune'}."
                )
            current = current[piece]
        else:
            raise ValueError(
                f"Chemin '{path}' : impossible de descendre dans "
                f"'{piece}', la valeur est un {type(current).__name__}."
            )
    return current


def _inject(template, message):
    """
    Put the message into the body template, in place of the marker.

    We work on the already-deserialised structure, not on text: a payload
    containing quotes or newlines therefore does not break the JSON, and
    cannot inject any either.
    """
    if isinstance(template, dict):
        return {cle: _inject(valeur, message) for cle, valeur in template.items()}
    if isinstance(template, list):
        return [_inject(valeur, message) for valeur in template]
    if template == MESSAGE_MARKER:
        return message
    return template


# --- Reply shapes other than "a JSON object" --------------------------------
# The adapter only accepted JSON, and that is the right default: working on the
# deserialised structure is what makes payload injection SAFE — the marker is
# replaced inside the parsed tree, so a payload stuffed with quotes and
# newlines travels intact and can break nothing.
#
# But two shapes really do turn up in front of a chatbot, and both are obtained
# without escaping anything by hand, since they concern ONLY how the reply is
# read — what we send stays JSON.

# Special path: take the whole body, exactly as it arrived. For a bespoke
# application that simply returns the bot's sentence.
RAW_TEXT_PATH = "@brut"

# Special path: the reply is a stream of events (server-sent events). The
# advice "turn streaming off" assumes you control the request body; when
# testing a client's APPLICATION — the most legitimate case — the endpoint
# sometimes streams with no way to stop it.
STREAM_PATH = "@flux:"


def _text_from_stream(brut, inner_path):
    """
    Glue the fragments of an SSE stream back into a single text.

    Format: "data: ..." lines separated by blank lines, with a final sentinel
    (`[DONE]` at most providers). Each fragment carries a piece of the reply,
    at the place described by `inner_path` — `choices.0.delta.content` in
    the OpenAI dialect.

    Unreadable fragments are IGNORED, not fatal: a stream contains comments,
    pings and control events, and stopping at the first would lose the whole
    reply when it is right there.
    """
    pieces = []
    for line in brut.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload_line = line[len("data:"):].strip()
        if not payload_line or payload_line == "[DONE]":
            continue
        try:
            fragment = _extract(json.loads(payload_line), inner_path)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(fragment, str):
            pieces.append(fragment)

    if not pieces:
        raise ValueError(
            f"Flux reçu, mais aucun fragment lisible en "
            f"'{inner_path}'.\n"
            f"  Vérifie le path INTERNE après « {STREAM_PATH} » : pour une "
            f"API de type OpenAI,\n"
            f"  c'est choices.0.delta.content."
        )
    return "".join(pieces)


def read_reply(brut, chemin_reponse):
    """
    Extract the text of a reply, as `chemin_reponse` describes it.

    - "@brut"                         -> the whole body, unparsed;
    - "@flux:choices.0.delta.content" -> an SSE stream, glued fragment by
      fragment;
    - "choices.0.message.content"     -> a dotted path into a JSON object.

    The first two are DECLARED special cases, never guessed: a reply that is
    not JSON stays an error by default, with its diagnosis. Guessing would let
    an HTML error page pass for a chatbot's answer, and the judge would end up
    scoring HTML.
    """
    if chemin_reponse == RAW_TEXT_PATH:
        return brut
    if chemin_reponse.startswith(STREAM_PATH):
        return _text_from_stream(brut, chemin_reponse[len(STREAM_PATH):])
    return _extract(json.loads(brut), chemin_reponse)


# What the target DECLARES in its `Content-Type` header, and the matching
# profile. This is the most reliable source: an application announces its
# format, so there is no need to sniff it.
#
# Never used to SWITCH reading mode, only to advise. A lying `Content-Type` —
# an error page announced as `application/json`, which plenty of gateways do —
# would then have the judge scoring HTML. The declaration guides the reader;
# the reader decides.
PROFILE_BY_DECLARED_TYPE = {
    "text/event-stream": "openai-flux",
    "text/plain": "texte",
    "text/html": None,          # pas un profil : une error d'adresse
}


def _advised_profile(declared_type):
    """The profile the declared Content-Type suggests, or None."""
    base = (declared_type or "").split(";")[0].strip().lower()
    return PROFILE_BY_DECLARED_TYPE.get(base)


def _diagnose(brut, declared_type=""):
    """
    Name the likely cause of a reply that is not JSON.

    "JSON expected" is accurate but says nothing about what to do, and two
    confusions come up constantly when wiring a target for the first time:
    giving the address of the chatbot's PAGE instead of its endpoint, and
    aiming at an API that replies as a stream.

    TWO sources, in this order: what the target DECLARES (`Content-Type`),
    then failing that what the body suggests. The declaration was added on
    2026-11-11, after the question "how is the format determined by the
    application?" — it already was, in a header the adapter threw away, and we
    were sniffing the first characters where one line above held the answer.
    """
    start = brut.lstrip()[:400].lower()

    # La déclaration d'abord : elle est explicite là où le reniflage déduit.
    advised = _advised_profile(declared_type)
    if advised:
        settings = TARGET_PROFILES[advised]
        return (f"  La cible ANNONCE « {declared_type.split(';')[0].strip()} » : "
                f"ce n'est pas un objet JSON.\n"
                f"  Le profil correspondant existe —\n"
                f"    --profil-cible {advised}\n"
                f"    ou CIBLE_CHEMIN_REPONSE={settings['chemin_reponse']}\n"
                f"  ({settings['description']})")

    declares_html = (declared_type or "").split(";")[0].strip().lower() \
        == "text/html"
    if (declares_html
            or start.startswith(("<!doctype", "<html", "<?xml"))
            or "<body" in start):
        return ("  C'est une PAGE WEB, pas un endpoint d'API : cet outil "
                "envoie un POST JSON.\n"
                "  Il faut l'adresse que la page appelle elle-même. Pour la "
                "trouver : ouvre le\n"
                "  chatbot dans un navigateur, outils de développement "
                "(F12), onglet Réseau,\n"
                "  envoie un message, et relève l'URL de la requête POST.")

    if start.startswith("data:") or "\ndata:" in start:
        return ("  Cette API répond en FLUX (server-sent events).\n"
                "  Deux issues : désactiver le flux si le corps te le permet "
                '("stream": false dans\n'
                "  CIBLE_CORPS), ou lire le flux tel quel —\n"
                f"    CIBLE_CHEMIN_REPONSE={STREAM_PATH}"
                "choices.0.delta.content\n"
                "    ou --profil-cible openai-flux\n"
                "  La seconde est la bonne quand tu testes l'application d'un "
                "client, qui ne\n"
                "  propose pas toujours de désactiver le flux.")

    if not start:
        return ("  La réponse est VIDE. Vérifie que l'URL est bien celle de "
                "l'endpoint, et que\n"
                "  la méthode attendue est un POST.")

    return ("  Vérifie que cette URL est l'endpoint de l'API, et non une "
            "page ou un proxy.")


def _first_defined(*values):
    """The first non-None value. `{}` and `""` stay valid choices."""
    return next((v for v in values if v is not None), None)


def _contains_marker(template):
    """Does the template have somewhere to put the payload?"""
    if isinstance(template, dict):
        return any(_contains_marker(v) for v in template.values())
    if isinstance(template, list):
        return any(_contains_marker(v) for v in template)
    return template == MESSAGE_MARKER


def check_template(corps):
    """
    Reject a body template with nowhere to put the payload.

    THE defect that justifies this function, and it is a serious one: `_inject`
    returns the template unchanged when the marker is missing. A typo
    (`{mesage}`), an omission, a body copied from some documentation — and the
    campaign sends the SAME fixed text on every attempt. The judge answers "no
    finding" every time, and the report concludes the target is safe.

    That is a silent false negative, the worst error for a security tool:
    nothing raises, nothing is missing, and the conclusion is inverted. Hence a
    refusal AT STARTUP rather than a check at send time — we do not want to
    discover this after spending a client's allowed throughput.
    """
    if _contains_marker(corps):
        return
    raise RuntimeError(
        f"Le template du corps ne contient pas le marqueur "
        f"« {MESSAGE_MARKER} » : le payload n'aurait nulle part où aller, "
        f"et la cible recevrait le même texte fixe à chaque essai.\n"
        f"  Gabarit lu : {json.dumps(corps, ensure_ascii=False)}\n"
        f"  Attendu, par exemple : "
        f'{{"message": "{MESSAGE_MARKER}"}}\n'
        f"  Vérifie CIBLE_CORPS dans .env (voir .env.example)."
    )


def build_http_target(url, entetes=None, corps=None, chemin_reponse=None,
                          delai=None, profil=None):
    """
    Return an `interroger(message) -> str` function aimed at `url`.

    Parameters left out are read from `.env` (see config.py):
    - entetes        : HTTP headers, authentication included;
    - corps          : JSON body template, where "{message}" gets replaced;
    - chemin_reponse : where to read the text in the JSON reply;
    - delai          : seconds before giving up;
    - profil         : a TARGET_PROFILES name, supplying `corps` and
                       `chemin_reponse` for a known API shape.

    Precedence: what is passed explicitly, then the profile, then `.env`. A
    profile is a CONVENIENCE, not a constraint: it must never override a
    setting made by hand.
    """
    from config import CIBLE_HTTP

    if profil is not None and profil not in TARGET_PROFILES:
        raise RuntimeError(
            f"Profil de cible inconnu : « {profil} ».\n"
            f"  Profils disponibles : {', '.join(TARGET_PROFILES)}."
        )
    settings = TARGET_PROFILES.get(profil, {})

    entetes = {**CIBLE_HTTP["entetes"], **(entetes or {})}
    corps = _first_defined(corps, settings.get("corps"), CIBLE_HTTP["corps"])
    chemin_reponse = _first_defined(
        chemin_reponse, settings.get("chemin_reponse"),
        CIBLE_HTTP["chemin_reponse"])
    delai = delai or CIBLE_HTTP["delai"]

    # BEFORE the first call: a whole campaign on a mute template would
    # conclude "no finding" without having sent any of what we believed.
    check_template(corps)

    def interroger(message):
        data = json.dumps(_inject(corps, message)).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", **entetes},
        )

        try:
            with urllib.request.urlopen(request, timeout=delai) as reponse:
                brut = reponse.read().decode("utf-8")
                # What the target DECLARES its format to be. Never used to
                # change reading mode — only to explain a failure better.
                # See `_diagnose`.
                declared_type = reponse.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            # The body of an HTTP error often holds the useful explanation
            # (rejected key, invalid format, quota): we surface it.
            detail = error.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Cible {url} : error HTTP {error.code}.\n  {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Cible {url} : injoignable ({error.reason}).\n"
                f"  Vérifie l'URL, le réseau, et que la cible est démarrée."
            ) from error

        try:
            texte = read_reply(brut, chemin_reponse)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Cible {url} : réponse illisible (JSON attendu).\n"
                f"  Annoncé par la cible : {declared_type or 'rien'}\n"
                f"  Reçu : {brut[:200]}\n"
                f"{_diagnose(brut, declared_type)}"
            ) from error
        except ValueError as error:
            # Chemin de réponse mal décrit : l'error dit déjà quoi corriger.
            raise RuntimeError(f"Cible {url} : {error}") from error

        if not isinstance(texte, str):
            raise RuntimeError(
                f"Cible {url} : '{chemin_reponse}' donne un "
                f"{type(texte).__name__}, pas du texte."
            )
        return texte


    # Single-turn, and declared as such (see cibles/conversation.py): the
    # `CIBLE_CORPS` template carries a single `{message}`, so we cannot yet
    # send several messages to an endpoint. A flat refusal beats a flattened
    # transcript that would later be taken for real multi-turn.
    interroger.conversation = False

    return interroger


# --- Vérification avant campagne ---------------------------------------------

# Ce qu'on envoie pour vérifier le branchement : anodin, et c'est voulu. Une
# vérification n'est pas une attaque — elle précède souvent le mandat, et elle
# ne doit rien laisser dans les journaux de la cible qui ressemble à un test
# d'intrusion.
PROBE_MESSAGE = "Bonjour, peux-tu me confirmer que tu me reçois ?"


def _plausible_paths(data, prefix="", depth=4):
    """
    Les chemins pointés qui mènent à du texte, dans une réponse JSON reçue.

    C'est ce qui transforme « clé absente » en « essaie plutôt ceci » : le
    path correct est presque toujours dans la liste, puisqu'il mène au texte
    que la cible vient de renvoyer.
    """
    if depth <= 0:
        return []
    trouves = []
    if isinstance(data, dict):
        for cle, valeur in data.items():
            path = f"{prefix}.{cle}" if prefix else str(cle)
            if isinstance(valeur, str) and valeur.strip():
                trouves.append((path, valeur))
            else:
                trouves += _plausible_paths(valeur, path, depth - 1)
    elif isinstance(data, list):
        for indice, valeur in enumerate(data[:3]):
            path = f"{prefix}.{indice}" if prefix else str(indice)
            if isinstance(valeur, str) and valeur.strip():
                trouves.append((path, valeur))
            else:
                trouves += _plausible_paths(valeur, path, depth - 1)
    return trouves


def probe_target(url, entetes=None, corps=None, chemin_reponse=None, delai=None,
           profil=None, show=print):
    """
    Envoie UN message anodin et rend compte, sans rien juger.

    Pourquoi cette commande existe : les messages d'error du projet sont
    bons, mais ils tombaient PENDANT la campagne, après qu'un payload soit
    déjà parti. Sur la cible d'un client, sous mandat, c'est consommer du
    débit autorisé et polluer la piste d'audit pour découvrir une coquille.
    Un appel anodin en amont déplace toutes ces erreurs avant le mandat.

    Renvoie True si le branchement fonctionne. Sur un path de réponse
    erroné, propose les chemins qui mènent à du texte dans la réponse reçue —
    le bon y est presque toujours.
    """
    from config import CIBLE_HTTP

    settings = TARGET_PROFILES.get(profil, {})
    corps_final = _first_defined(corps, settings.get("corps"),
                                  CIBLE_HTTP["corps"])
    chemin_final = _first_defined(chemin_reponse,
                                   settings.get("chemin_reponse"),
                                   CIBLE_HTTP["chemin_reponse"])

    show(f"Cible    : {url}")
    if profil:
        show(f"Profil   : {profil} — {settings['description']}")
    show(f"Corps    : {json.dumps(corps_final, ensure_ascii=False)}")
    show(f"Chemin   : {chemin_final}")
    entetes_finaux = {**CIBLE_HTTP["entetes"], **(entetes or {})}
    # On nomme les en-têtes sans montrer leur valeur : un jeton n'a rien à
    # faire dans une sortie de terminal qu'on colle dans un rapport ou un chat.
    show(f"En-têtes : {', '.join(entetes_finaux) or 'aucun'}"
             + (" (values masquées)" if entetes_finaux else ""))
    show("")

    try:
        check_template(corps_final)
    except RuntimeError as error:
        show(f"ÉCHEC — {error}")
        return False

    interroger = build_http_target(url, entetes, corps_final,
                                       chemin_final, delai, profil=None)
    show(f"Envoi    : {PROBE_MESSAGE}")
    try:
        reponse = interroger(PROBE_MESSAGE)
    except RuntimeError as error:
        show(f"\nÉCHEC — {error}")
        _suggest(url, entetes_finaux, corps_final, delai, show)
        return False

    show(f"Réponse  : {reponse[:300]}"
             + (" […]" if len(reponse) > 300 else ""))
    show("\nBranchement VALIDE : la cible répond et le texte se lit bien.")
    return True


def _suggest(url, entetes, corps, delai, show):
    """Relit la réponse brute pour proposer un path qui mène à du texte."""
    request = urllib.request.Request(
        url, data=json.dumps(_inject(corps, PROBE_MESSAGE)).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **entetes})
    try:
        with urllib.request.urlopen(request, timeout=delai or 60) as reponse:
            data = json.loads(reponse.read().decode("utf-8"))
    except Exception:
        # La suggestion est un bonus : si elle échoue, l'error d'origine
        # reste affichée et c'est elle qui compte.
        return

    chemins = _plausible_paths(data)
    if not chemins:
        return
    show("\nChemins qui mènent à du texte dans la réponse reçue :")
    for path, valeur in chemins[:6]:
        extrait = valeur.replace("\n", " ")[:60]
        show(f"  CIBLE_CHEMIN_REPONSE={path}")
        show(f"      → {extrait!r}")

    # Si AUCUN texte reçu ne reprend ce qu'on a envoyé, c'est que la cible ne
    # l'a pas vu : le corps est faux lui aussi, et corriger le seul path ne
    # suffira pas. Sans cet indice, on lirait « choices.0.message.content »
    # comme la solution, on relancerait, et la cible répondrait toujours à
    # côté — en consommant du débit à chaque essai.
    extrait_envoye = PROBE_MESSAGE[:20]
    if not any(extrait_envoye in valeur for _, valeur in chemins):
        show("\nAttention : aucun de ces textes ne reprend le message "
                 "envoyé.\n  La cible ne l'a donc pas reçu là où elle "
                 "l'attendait : CIBLE_CORPS est à corriger aussi, pas "
                 "seulement le path.\n  Essaie --profil-cible "
                 f"{', '.join(TARGET_PROFILES)} pour partir d'une forme connue.")
