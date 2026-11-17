"""
targets/http.py — Aiming at a real endpoint.

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

NOTE ON NAMING (2026-11-13). The `.env` keys (`TARGET_BODY`,
`TARGET_RESPONSE_PATH`, `TARGET_HEADERS`) and the profile dictionaries' keys
stay French: they are a CONFIGURATION contract. Renaming them would break every
existing `.env`, including those on machines this repository never sees. They
move with the coordinated data-key pass, with a documented migration. See
`GLOSSARY.md`.
"""

import copy
import json
import urllib.error
import urllib.request

# Token replaced by the payload inside the request body.
MESSAGE_MARKER = "{message}"


# --- Target profiles: the shapes met in practice -----------------------------
# Describing `TARGET_BODY` and `TARGET_RESPONSE_PATH` by hand means reading the
# API's documentation, then writing nested JSON inside an environment variable.
# It is the most tedious part of wiring a target, and for the MOST COMMON case
# it is entirely predictable: most LLM endpoints speak the OpenAI dialect.
#
# These profiles do not replace manual configuration, they cover the known
# cases. A bespoke application keeps its own shape in `.env`, and that is
# precisely why the project never guesses: it offers.
TARGET_PROFILES = {
    "openai": {
        "body": {"messages": [{"role": "user", "content": MESSAGE_MARKER}]},
        "response_path": "choices.0.message.content",
        "description": "OpenAI-style API (OpenAI, Groq, Together, vLLM, "
                       "LM Studio, most gateways)",
    },
    "ollama": {
        "body": {"model": "llama3.2", "prompt": MESSAGE_MARKER,
                  "stream": False},
        "response_path": "response",
        "description": "Ollama directly (/api/generate), no OpenAI layer",
    },
    "anthropic": {
        "body": {"messages": [{"role": "user", "content": MESSAGE_MARKER}],
                  "max_tokens": 1024},
        "response_path": "content.0.text",
        "description": "Anthropic's Messages API",
    },
    "simple": {
        "body": {"message": MESSAGE_MARKER},
        "response_path": "reply",
        "description": "bespoke app: {\"message\": …} → {\"reply\": …}",
    },
    # For an application whose request body we do not control, and which
    # streams without any way to stop it — the case of a client application
    # tested under mandate.
    "openai-flux": {
        "body": {"messages": [{"role": "user", "content": MESSAGE_MARKER}],
                  "stream": True},
        "response_path": "@flux:choices.0.delta.content",
        "description": "OpenAI-style API replying as a stream (SSE)",
    },
    "text": {
        "body": {"message": MESSAGE_MARKER},
        "response_path": "@brut",
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
                    f"Path '{path}': '{piece}' is not an index, while the "
                    f"reply holds a list at that point."
                )
            current = current[int(piece)]
        elif isinstance(current, dict):
            if piece not in current:
                raise ValueError(
                    f"Path '{path}': key '{piece}' missing. "
                    f"Keys available: {', '.join(current) or 'none'}."
                )
            current = current[piece]
        else:
            raise ValueError(
                f"Path '{path}': cannot descend into '{piece}', the value "
                f"is a {type(current).__name__}."
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
            f"Stream received, but no readable fragment at "
            f"'{inner_path}'.\n"
            f'  Check the INNER path after "{STREAM_PATH}": for an '
            f"OpenAI-shaped API,\n"
            f"  it is choices.0.delta.content."
        )
    return "".join(pieces)


def read_reply(brut, response_path):
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
    if response_path == RAW_TEXT_PATH:
        return brut
    if response_path.startswith(STREAM_PATH):
        return _text_from_stream(brut, response_path[len(STREAM_PATH):])
    return _extract(json.loads(brut), response_path)


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
    "text/plain": "text",
    "text/html": None,          # not a profile: a wrong address
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
        return (f'  The target DECLARES '
                f'"{declared_type.split(";")[0].strip()}": that is not a '
                f"JSON object.\n"
                f"  The matching profile exists —\n"
                f"    --target-profile {advised}\n"
                f"    or TARGET_RESPONSE_PATH={settings['response_path']}\n"
                f"  ({settings['description']})")

    declares_html = (declared_type or "").split(";")[0].strip().lower() \
        == "text/html"
    if (declares_html
            or start.startswith(("<!doctype", "<html", "<?xml"))
            or "<body" in start):
        return ("  This is a WEB PAGE, not an API endpoint: this tool sends "
                "a JSON POST.\n"
                "  You need the address the page calls itself. To find it: "
                "open the chatbot\n"
                "  in a browser, developer tools (F12), Network tab, send a "
                "message, and\n"
                "  read off the URL of the POST request.")

    if start.startswith("data:") or "\ndata:" in start:
        return ("  This API answers as a STREAM (server-sent events).\n"
                "  Two ways out: switch the stream off if the body lets you "
                '("stream": false in\n'
                "  TARGET_BODY), or read the stream as it is —\n"
                f"    TARGET_RESPONSE_PATH={STREAM_PATH}"
                "choices.0.delta.content\n"
                "    or --target-profile openai-flux\n"
                "  The second is the right one when you are testing a "
                "client's application,\n"
                "  which does not always offer to switch the stream off.")

    if not start:
        return ("  The reply is EMPTY. Check that the URL really is the "
                "endpoint's, and that\n"
                "  the expected method is a POST.")

    return ("  Check that this URL is the API's endpoint, and not a page or "
            "a proxy.")


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


# The role names we recognise in a body template, and the counterpart to use
# for the target's own turns. The USER name is what we look for -- it is the
# one the operator wrote beside the marker -- and the ASSISTANT name is what a
# past reply of the target becomes.
#
# Deliberately short: these two pairs cover the OpenAI-compatible APIs, the
# Anthropic Messages API and the gateways that imitate them, which is what
# `TARGET_PROFILES` already describes. An API using other names is not
# guessed at: no slot is found, `conversation` stays False, and the refusal
# says what is missing. Silence means refusal, never permission.
ROLE_PAIRS = {"user": "assistant", "human": "ai"}


def history_slot(template):
    """
    Where a conversation's past turns can go, or None.

    Returns `(path, index, role_key, role_names)`: the list that holds the
    marker's element, that element's position in it, the key carrying the
    role, and the pair of role names to use.

    THE RULE, and it is the reason this is honest rather than clever: we do
    not invent the API's turn shape, we COPY the one the operator wrote. If
    the body is `{"messages": [{"role": "user", "content": "{message}"}]}`,
    then a past turn of the target is that same object with its role swapped
    -- same keys, same order, nothing added. An inferred shape would be a
    guess about the target, which this adapter refuses everywhere else.

    No list, or no recognisable role beside the marker, means no slot: the
    `{"prompt": "{message}"}` shape of the `ollama` and `simple` profiles has
    nowhere to put a dialogue, and that is a fact about the endpoint, not a
    limitation to work around by pasting a transcript into one message.
    """
    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                found = walk(value, path + [key])
                if found:
                    return found
        elif isinstance(node, list):
            for index, element in enumerate(node):
                # The element itself must be a dict holding the marker as one
                # of its own values, beside a role we recognise.
                if isinstance(element, dict) and _contains_marker(element):
                    for key, value in element.items():
                        names = ROLE_PAIRS.get(str(value).lower())
                        if names:
                            return (path, index, key,
                                    (str(value), names))
                found = walk(element, path + [index])
                if found:
                    return found
        return None

    return walk(template, [])


def _at(structure, path):
    """The node `path` names, inside `structure`."""
    for piece in path:
        structure = structure[piece]
    return structure


def with_history(template, history):
    """
    The body template with the past turns inserted before the marker.

    Returns a NEW structure: the template is reused across attempts, and
    mutating it would leak one conversation's turns into the next.

    A history with no slot to go in RAISES rather than being dropped. Dropping
    it is exactly the defect this whole contract exists to prevent: the
    orchestrator would believe it was holding a dialogue while the endpoint
    saw isolated messages, and "multi-turn brings nothing" would be a false
    conclusion that nothing contradicts.
    """
    if not history:
        return template

    slot = history_slot(template)
    if slot is None:
        raise RuntimeError(
            f"This endpoint's body template cannot carry a conversation: the "
            f'marker "{MESSAGE_MARKER}" is not inside a list of turns.\n'
            f"  Template read: {json.dumps(template, ensure_ascii=False)}\n"
            f"  A template that CAN: "
            f'{{"messages": [{{"role": "user", "content": '
            f'"{MESSAGE_MARKER}"}}]}}\n'
            f"  Profiles with one: "
            f"{', '.join(n for n, s in TARGET_PROFILES.items() if history_slot(s['body']))}.\n"
            f"  Otherwise, run a single-turn campaign: the dialogue is NOT "
            f"flattened into one message, because a model can refuse a role "
            f"attributed to it in a transcript after accepting it turn by "
            f"turn. That is not the same measurement.")

    path, index, role_key, (user_name, assistant_name) = slot
    body = copy.deepcopy(template)
    turns = _at(body, path)
    shape = turns[index]

    past = []
    for turn in history:
        # The template's own element, with the role swapped and the marker
        # replaced by this turn's text. Same keys: whatever else the operator
        # put in that object (a name, a type) is carried through untouched.
        api_role = (assistant_name if turn.get("role") == "assistant"
                    else user_name)
        past.append({key: (turn["content"] if value == MESSAGE_MARKER
                           else api_role if key == role_key
                           else value)
                     for key, value in shape.items()})

    turns[index:index] = past
    return body


def check_template(body):
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
    if _contains_marker(body):
        return
    raise RuntimeError(
        f'The body template does not hold the marker "{MESSAGE_MARKER}": '
        f"the payload would have nowhere to go, and the target would receive "
        f"the same fixed text on every attempt.\n"
        f"  Template read: {json.dumps(body, ensure_ascii=False)}\n"
        f"  Expected, for instance: "
        f'{{"message": "{MESSAGE_MARKER}"}}\n'
        f"  Check TARGET_BODY in .env (see .env.example)."
    )


def build_http_target(url, headers=None, body=None, response_path=None,
                          timeout=None, profile=None):
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
    from config import HTTP_TARGET

    if profile is not None and profile not in TARGET_PROFILES:
        raise RuntimeError(
            f"Profil de cible inconnu : « {profile} ».\n"
            f"  Profils disponibles : {', '.join(TARGET_PROFILES)}."
        )
    settings = TARGET_PROFILES.get(profile, {})

    headers = {**HTTP_TARGET["headers"], **(headers or {})}
    body = _first_defined(body, settings.get("body"), HTTP_TARGET["body"])
    response_path = _first_defined(
        response_path, settings.get("response_path"),
        HTTP_TARGET["response_path"])
    timeout = timeout or HTTP_TARGET["timeout"]

    # BEFORE the first call: a whole campaign on a mute template would
    # conclude "no finding" without having sent any of what we believed.
    check_template(body)

    def interroger(message, history=None):
        data = json.dumps(
            _inject(with_history(body, history), message)).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", **headers},
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                brut = reply.read().decode("utf-8")
                # What the target DECLARES its format to be. Never used to
                # change reading mode — only to explain a failure better.
                # See `_diagnose`.
                declared_type = reply.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            # The body of an HTTP error often holds the useful explanation
            # (rejected key, invalid format, quota): we surface it.
            detail = error.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Target {url}: HTTP error {error.code}.\n  {detail}"
            ) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Target {url}: unreachable ({error.reason}).\n"
                f"  Check the URL, the network, and that the target is up."
            ) from error

        try:
            texte = read_reply(brut, response_path)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Target {url}: unreadable reply (JSON expected).\n"
                f"  Declared by the target: {declared_type or 'nothing'}\n"
                f"  Received: {brut[:200]}\n"
                f"{_diagnose(brut, declared_type)}"
            ) from error
        except ValueError as error:
            # Chemin de réponse mal décrit : l'error dit déjà quoi corriger.
            raise RuntimeError(f"Target {url}: {error}") from error

        if not isinstance(texte, str):
            raise RuntimeError(
                f"Target {url}: '{response_path}' gives a "
                f"{type(texte).__name__}, not text."
            )
        return texte


    # DECLARED from the template, not decided in advance (verrou 2,
    # 2026-11-17). This was a flat `False`, which made the multi-turn
    # orchestrator usable on the bundled targets and NOT on a real endpoint --
    # the one place phase 3b was wanted.
    #
    # It is still a declaration and never a guess: True only when the body
    # really has somewhere to put the turns, so a `{"prompt": "{message}"}`
    # endpoint keeps refusing. And the refusal keeps its reason: we do not
    # flatten a dialogue into one message, because a model can refuse a role
    # attributed to it in a transcript after accepting it turn by turn.
    interroger.conversation = history_slot(body) is not None

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


def probe_target(url, headers=None, body=None, response_path=None, timeout=None,
           profile=None, show=print):
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
    from config import HTTP_TARGET

    settings = TARGET_PROFILES.get(profile, {})
    corps_final = _first_defined(body, settings.get("body"),
                                  HTTP_TARGET["body"])
    chemin_final = _first_defined(response_path,
                                   settings.get("response_path"),
                                   HTTP_TARGET["response_path"])

    show(f"Target   : {url}")
    if profile:
        show(f"Profile  : {profile} — {settings['description']}")
    show(f"Body     : {json.dumps(corps_final, ensure_ascii=False)}")
    show(f"Path     : {chemin_final}")
    entetes_finaux = {**HTTP_TARGET["headers"], **(headers or {})}
    # On nomme les en-têtes sans montrer leur valeur : un jeton n'a rien à
    # faire dans une sortie de terminal qu'on colle dans un rapport ou un chat.
    show(f"Headers  : {', '.join(entetes_finaux) or 'none'}"
         + (" (values hidden)" if entetes_finaux else ""))
    # Said HERE, before any campaign, because `--multiturn` is a choice the
    # operator makes on the command line and the answer depends on the body
    # THEY wrote. Discovering it when the campaign refuses would mean having
    # already armed the budget and opened an audit trail.
    if history_slot(corps_final) is not None:
        show("Multiturn: yes — the turns go in the list holding the marker, "
             "so `--multiturn` works against this endpoint.")
    else:
        show("Multiturn: NO — the marker is not inside a list of turns, so "
             "there is nowhere to put a dialogue. A single-turn campaign "
             "works; `--multiturn` will refuse rather than flatten the "
             "conversation into one message.")
    show("")

    try:
        check_template(corps_final)
    except RuntimeError as error:
        show(f"FAILED — {error}")
        return False

    interroger = build_http_target(url, headers, corps_final,
                                       chemin_final, timeout, profile=None)
    show(f"Sending  : {PROBE_MESSAGE}")
    try:
        reply = interroger(PROBE_MESSAGE)
    except RuntimeError as error:
        show(f"\nFAILED — {error}")
        _suggest(url, entetes_finaux, corps_final, timeout, show)
        return False

    show(f"Reply    : {reply[:300]}"
         + (" […]" if len(reply) > 300 else ""))
    show("\nWiring VALID: the target answers and the text reads correctly.")
    return True


def _suggest(url, headers, body, timeout, show):
    """Relit la réponse brute pour proposer un path qui mène à du texte."""
    request = urllib.request.Request(
        url, data=json.dumps(_inject(body, PROBE_MESSAGE)).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout or 60) as reply:
            data = json.loads(reply.read().decode("utf-8"))
    except Exception:
        # La suggestion est un bonus : si elle échoue, l'error d'origine
        # reste affichée et c'est elle qui compte.
        return

    chemins = _plausible_paths(data)
    if not chemins:
        return
    show("\nPaths that lead to text in the reply received:")
    for path, valeur in chemins[:6]:
        extrait = valeur.replace("\n", " ")[:60]
        show(f"  TARGET_RESPONSE_PATH={path}")
        show(f"      → {extrait!r}")

    # Si AUCUN texte reçu ne reprend ce qu'on a envoyé, c'est que la cible ne
    # l'a pas vu : le corps est faux lui aussi, et corriger le seul path ne
    # suffira pas. Sans cet indice, on lirait « choices.0.message.content »
    # comme la solution, on relancerait, et la cible répondrait toujours à
    # côté — en consommant du débit à chaque essai.
    extrait_envoye = PROBE_MESSAGE[:20]
    if not any(extrait_envoye in valeur for _, valeur in chemins):
        show("\nWarning: none of these texts echoes the message that was "
             "sent.\n  The target therefore did not receive it where it "
             "expected: TARGET_BODY needs fixing too, not just the path."
             "\n  Try --target-profile "
             f"{', '.join(TARGET_PROFILES)} to start from a known shape.")
