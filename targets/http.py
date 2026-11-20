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
import secrets
import urllib.error
import urllib.parse
import urllib.request

# NOTE: `targets/websocket.py` is imported LAZILY, inside the one function
# that sends over a socket. `targets/__init__.py` imports THIS module at
# import time, so a module-level import of a sibling would be circular --
# `targets` would be half-initialised and the attribute not yet bound. Same
# reason `from config import HTTP_TARGET` sits inside its callers here.

# Token replaced by the payload inside the request body.
MESSAGE_MARKER = "{message}"


# --- Transports: the request shapes other than "a JSON POST" ----------------
# A JSON POST covers almost every LLM endpoint, and it stays the default. But
# three other shapes really do sit in front of a chatbot, and all three were
# recorded in this project as out of reach:
#
#   - GET, payload in the query string: a small bespoke service, or a chatbot
#     behind a gateway that only exposes reads;
#   - multipart/form-data: an application that accepts a prompt beside a file;
#   - WebSocket: what a browser chat widget usually opens.
#
# The transport is DECLARED, like everything else in this adapter: a profile
# names it, `.env` can set it, the command line wins. See `resolve_transport`
# for the one case that is derived rather than declared, and why that one is
# not a guess.
JSON_POST = "json-post"
GET_QUERY = "get"
MULTIPART = "multipart"
WEBSOCKET = "websocket"

TRANSPORTS = {
    JSON_POST: "POST, a JSON body (the default: almost every LLM API)",
    GET_QUERY: "GET, the payload in the query string",
    MULTIPART: "POST, multipart/form-data (a form, not JSON)",
    WEBSOCKET: "WebSocket, ws:// or wss://, one frame per turn",
}


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
    # The three transports other than a JSON POST. Their bodies are FLAT on
    # purpose: a query string and a form body are key-to-value, so a nested
    # template has no meaning there and is refused rather than flattened.
    "get": {
        "body": {"q": MESSAGE_MARKER},
        "response_path": "reply",
        "transport": GET_QUERY,
        "description": "GET with the payload in the query string",
    },
    "multipart": {
        "body": {"message": MESSAGE_MARKER},
        "response_path": "reply",
        "transport": MULTIPART,
        "description": "multipart/form-data POST, as an HTML form sends",
    },
    "websocket": {
        "body": {"message": MESSAGE_MARKER},
        "response_path": "reply",
        "transport": WEBSOCKET,
        "description": "WebSocket (ws:// or wss://), one JSON frame per turn",
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


class PayloadTooLong(RuntimeError):
    """
    A payload that cannot be DELIVERED by the chosen transport.

    Distinct from a wiring failure, and for the same reason `BudgetExceeded`
    is distinct from an error: it is not the target refusing, and it is not
    the campaign broken. It is one attempt that never happened, so the
    orchestrator records it as a MISSING measurement -- outside the ASR
    denominator -- and carries on with the next.
    """


#: The longest URL a GET attempt may build before it is refused.
#:
#: THE DEFECT THIS EXISTS FOR, because the number matters less than the
#: refusal: garak payloads run past 2,500 characters and percent-encoding can
#: add half again. Servers cap the request line -- 2,083 was Internet
#: Explorer's historical floor and gateways still use figures of that order --
#: and a cap is enforced by TRUNCATING. So the target would receive a payload
#: cut in half, answer something harmless, the judge would say "no finding"
#: and the report would conclude the target is safe.
#:
#: That is the silent false negative this project hunts, in its purest form:
#: nothing raises, nothing is missing, and the conclusion is INVERTED. Worse
#: than the truncated-reply case, where the reply at least carries the sign of
#: its own truncation -- here nothing does.
#:
#: Hence a REFUSAL, never a truncation, and a conservative default. An
#: operator who knows their server takes 8 kB raises TARGET_URL_LIMIT rather
#: than losing the long payloads: a limit set too low costs coverage, and
#: silently dropping a quarter of the library would be its own lie.
URL_LIMIT = 2000

#: Draws allowed when looking for a multipart boundary absent from the
#: payload. Bounded, like every loop in this project.
BOUNDARY_DRAWS = 8


def _flat_fields(structure, transport):
    """
    The body as key-to-value pairs, or a refusal.

    A query string and a form body are flat by nature. A nested template has
    no meaning in either, and flattening one ourselves would be inventing a
    convention the target never declared -- the thing this adapter refuses
    everywhere else. So it refuses, and names the shape that works.

    Non-string values go through `json.dumps`, so `False` becomes `false` and
    not Python's `False`: an API reading a form field expects the former.
    """
    if not isinstance(structure, dict) or not structure:
        raise RuntimeError(
            f"The {transport} transport needs a FLAT body of named fields.\n"
            f"  Template read: {json.dumps(structure, ensure_ascii=False)}\n"
            f'  Expected, for instance: {{"q": "{MESSAGE_MARKER}"}}')

    fields = {}
    for name, value in structure.items():
        if isinstance(value, (dict, list)):
            raise RuntimeError(
                f"The {transport} transport cannot carry a nested body: the "
                f"field '{name}' holds a "
                f"{'list' if isinstance(value, list) else 'object'}.\n"
                f"  A query string and a form body are key-to-value; "
                f"flattening this one\n"
                f"  ourselves would invent a convention the target never "
                f"declared.\n"
                f"  Use a flat TARGET_BODY, or the json-post transport, "
                f"which does carry nesting.")
        fields[str(name)] = (value if isinstance(value, str)
                             else json.dumps(value))
    return fields


def _query_url(url, fields):
    """
    The URL with the fields added to its query string.

    `urlencode` does the percent-encoding, which is this transport's whole
    safety argument: the recorded rule is that what we SEND stays structured,
    "because an attack payload is designed to twist escaping". A query string
    is not JSON, but the escaping is still delegated to the standard library
    rather than done by hand -- and an existing query in the URL is kept,
    not overwritten.
    """
    parts = urllib.parse.urlsplit(url)
    added = urllib.parse.urlencode(fields)
    query = f"{parts.query}&{added}" if parts.query else added
    return urllib.parse.urlunsplit(parts._replace(query=query))


def _refuse_a_long_url(full, limit):
    """Refuse a URL over the limit, rather than let a server truncate it."""
    if len(full) <= limit:
        return
    raise PayloadTooLong(
        f"Payload NOT SENT: the URL it builds is {len(full)} characters, "
        f"over the {limit} this transport allows.\n"
        f"  It is refused rather than truncated: a server that cuts the "
        f"request line would\n"
        f"  deliver half a payload, the target would answer harmlessly, and "
        f"the report would\n"
        f"  conclude the target is safe. Nothing would flag it.\n"
        f"  Ways out: an endpoint that takes a POST (--target-profile "
        f"simple), raising\n"
        f"  TARGET_URL_LIMIT if you know what your server accepts, or "
        f"--excluding on the\n"
        f"  technique whose payloads are this long.")


def _boundary_for(values):
    """
    A multipart boundary that appears in none of the values.

    THE DEFECT THIS GUARDS, and it is the one real injection risk among the
    three transports: a multipart body is delimited by a text marker, nothing
    escapes it, and an attack payload is text we did not write. A payload
    carrying our boundary would end its part early and the target would parse
    something other than what we meant to send.

    `report._fence()` met the same problem in Markdown and answered by
    LENGTHENING the marker with NO CAP -- a first version capped it at twelve
    backticks and recreated the bug it was meant to prevent. The lesson
    holds; the mechanism cannot, because RFC 2046 caps a boundary at 70
    characters. So: draw at random, VERIFY rather than assume, re-draw on a
    collision, and REFUSE if it somehow persists. A corrupt body is never
    sent.
    """
    for _ in range(BOUNDARY_DRAWS):
        boundary = "----pentestllm" + secrets.token_hex(20)
        if not any(boundary in value for value in values):
            return boundary
    raise RuntimeError(                                    # pragma: no cover
        "multipart: no boundary found that the payload does not contain. "
        "The body is NOT sent: a boundary inside the payload would make the "
        "target parse something other than what we meant to send.")


def _multipart_body(fields):
    """
    A `multipart/form-data` body, and the Content-Type that describes it.

    Fields only, and that boundary is worth stating: a FILE part is what an
    indirect-injection test would need -- a payload reaching the model through
    a document rather than from the user -- and indirect injection is one of
    the registers the judge cannot score at all. Building the transport for a
    measurement that cannot be made would be building the wrong half first.
    """
    boundary = _boundary_for(fields.values())
    pieces = []
    for name, value in fields.items():
        if any(character in name for character in '"\r\n'):
            raise RuntimeError(
                f"multipart: the field name {name!r} holds a quote or a line "
                f"break, which cannot be written into a Content-Disposition "
                f"header. Rename it in TARGET_BODY.")
        pieces.append(f"--{boundary}\r\n"
                      f'Content-Disposition: form-data; name="{name}"\r\n'
                      f"\r\n{value}\r\n")
    pieces.append(f"--{boundary}--\r\n")
    return ("".join(pieces).encode("utf-8"),
            f"multipart/form-data; boundary={boundary}")


def _frame_text(structure):
    """
    What one WebSocket frame carries.

    A dict goes as JSON, like every other transport here. But a template that
    is JUST the marker sends the payload BARE, and that is a deliberate
    exception to "the outgoing side stays JSON, always".

    The rule's reason is escaping: in a raw HTTP body "you would have to
    escape by hand, and an attack payload is designed to twist escaping". A
    WebSocket frame is LENGTH-prefixed -- no delimiter, no terminator,
    nothing to escape and so nothing to twist. Refusing the bare form would
    be applying the rule's letter against its reason, and plenty of chat
    sockets take a bare sentence.
    """
    return (structure if isinstance(structure, str)
            else json.dumps(structure, ensure_ascii=False))


def resolve_transport(url, transport, from_profile, from_env):
    """
    Which transport to use: the command line, then the profile, then `.env`.

    One case is DERIVED rather than declared: a `ws://` or `wss://` URL with
    nothing else said means WebSocket. That is not the kind of guess this
    adapter refuses elsewhere -- a `Content-Type` is a CLAIM about content and
    plenty of gateways lie in it, which is why it only ever advises here,
    whereas a URL scheme IS the protocol. You cannot POST to a `ws://`
    address.

    And a contradiction RAISES rather than being resolved quietly: a declared
    transport the scheme cannot carry is a mistake, and picking a winner for
    the operator would hide it.
    """
    chosen = _first_defined(transport, from_profile, from_env)
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if chosen is None:
        chosen = WEBSOCKET if scheme in ("ws", "wss") else JSON_POST

    if chosen not in TRANSPORTS:
        raise RuntimeError(
            f"Unknown transport: « {chosen} ».\n"
            + "\n".join(f"  {name} — {what}"
                        for name, what in TRANSPORTS.items()))

    if chosen == WEBSOCKET and scheme not in ("ws", "wss"):
        raise RuntimeError(
            f"The websocket transport needs a ws:// or wss:// URL, and this "
            f"one is {scheme}://.\n"
            f"  The two cannot be mixed: a WebSocket is not an HTTP request "
            f"with a header on it.\n"
            f"  Find the right address in the browser's developer tools, "
            f"Network tab, filter WS.")
    if chosen != WEBSOCKET and scheme in ("ws", "wss"):
        raise RuntimeError(
            f"This URL is a WebSocket ({scheme}://) and the {chosen} "
            f"transport speaks HTTP.\n"
            f"  Nothing can POST to a ws:// address. Either use "
            f"--target-profile websocket,\n"
            f"  or give the endpoint's http(s):// address if it has one.")
    return chosen


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
        # An SSE stream labels each line `data:`. A WEBSOCKET sends the very
        # same JSON objects as frames, with no label to carry -- so a line
        # that parses as JSON on its own counts too, and one reader serves
        # both. Nothing else loosens: a line that does not parse is still
        # ignored, which is what keeps comments, pings and `[DONE]` out.
        if not line.startswith("data:") and not line.startswith("{"):
            continue
        payload_line = line[len("data:"):].strip() \
            if line.startswith("data:") else line
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


def _diagnose(brut, declared_type="", transport=JSON_POST):
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
        if transport == WEBSOCKET:
            # "the expected method is a POST" is wrong advice on a socket,
            # and wrong advice costs more than none: it sends the operator
            # to check a thing that does not apply.
            return ("  The reply is EMPTY. The handshake worked, so the "
                    "address is right: the\n"
                    "  endpoint probably expects a different frame SHAPE "
                    "(check TARGET_BODY), or\n"
                    "  an authentication frame this client does not send.")
        return (f"  The reply is EMPTY. Check that the URL really is the "
                f"endpoint's, and that\n"
                f"  the expected method is a "
                f"{'GET' if transport == GET_QUERY else 'POST'}.")

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


def _raw_reply(transport, url, headers, structure, timeout, quiet, limit,
               stream=False):
    """
    The target's reply, undecoded, whatever transport carries it.

    Returns `(body, declared_type, ended)`. `ended` only means something over
    a WebSocket, where a reply stops either on the server's close frame or on
    the silence window -- and the difference is a diagnosis `probe_target`
    passes on, because the second may have lost a tail.

    One function for the four transports, used by the campaign AND by
    `probe_target`'s path suggestion. Two copies would have drifted on the
    first transport added, and the suggestion would then have been POSTing
    JSON at an endpoint the campaign reaches by GET.
    """
    if transport == WEBSOCKET:
        # Imported here, not at module level: see the note by the imports.
        from targets import websocket as ws

        reply = ws.ask_over_websocket(
            url, _frame_text(structure), headers=headers, timeout=timeout,
            quiet=ws.QUIET_SECONDS if quiet is None else quiet)
        # The frames hold one JSON object each when the endpoint streams, so
        # the stream reader needs them on separate lines; a plain-text bot
        # sends its sentence in pieces, where a newline between them would
        # corrupt it. The TRANSPORT reports what arrived, the READER decides
        # how to read it -- as with the declared Content-Type.
        return (("\n".join(reply.frames) if stream else reply.text),
                "", reply.ended)

    if transport == GET_QUERY:
        full = _query_url(url, _flat_fields(structure, GET_QUERY))
        _refuse_a_long_url(full, URL_LIMIT if limit is None else limit)
        # No Content-Type: a GET carries no body, and announcing one would
        # describe something that is not there.
        request = urllib.request.Request(full, method="GET", headers=headers)
    elif transport == MULTIPART:
        data, content_type = _multipart_body(
            _flat_fields(structure, MULTIPART))
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": content_type, **headers})
    else:
        data = json.dumps(structure).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", **headers})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return (reply.read().decode("utf-8"),
                    # What the target DECLARES its format to be. Never used
                    # to change reading mode -- only to explain a failure
                    # better. See `_diagnose`.
                    reply.headers.get("Content-Type", ""), "close")
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


def build_http_target(url, headers=None, body=None, response_path=None,
                          timeout=None, profile=None, transport=None):
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
    transport = resolve_transport(url, transport, settings.get("transport"),
                                  HTTP_TARGET["transport"])
    limit = HTTP_TARGET["url_limit"]
    quiet = HTTP_TARGET["ws_quiet"]

    # BEFORE the first call: a whole campaign on a mute template would
    # conclude "no finding" without having sent any of what we believed.
    check_template(body)
    # And before the first call too, for the same reason: a flat-body
    # transport given a nested template must refuse at STARTUP, not after a
    # payload has gone out and a client's throughput has been spent.
    if transport in (GET_QUERY, MULTIPART):
        _flat_fields(_inject(body, "probe"), transport)

    def interroger(message, history=None):
        brut, declared_type, ended = _raw_reply(
            transport, url, headers,
            _inject(with_history(body, history), message),
            timeout, quiet, limit,
            stream=str(response_path).startswith(STREAM_PATH))

        # HOW the exchange ended, recorded on the function rather than
        # returned: the contract is `ask(message) -> str` and every caller
        # depends on it. `probe_target` reads it to say whether a WebSocket
        # reply stopped on a close frame or on the silence window -- WITHOUT
        # asking a second time. A first version re-sent the probe message to
        # find out, which quietly doubled what a verification leaves in a
        # client's logs, against PROBE_MESSAGE's own stated contract.
        interroger.ended = ended

        try:
            texte = read_reply(brut, response_path)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Target {url}: unreadable reply (JSON expected).\n"
                f"  Declared by the target: {declared_type or 'nothing'}\n"
                f"  Received: {brut[:200]}\n"
                f"{_diagnose(brut, declared_type, transport)}"
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
    #
    # The three transports added on 2026-11-20 inherit this unchanged, and
    # for GET and multipart it answers NO on its own: a flat body has no list
    # of turns. Over a WebSocket a body that IS a list of turns works, while
    # the OTHER multi-turn shape a socket allows -- the dialogue kept on the
    # connection, turn after turn on one socket -- is NOT supported: our
    # contract hands each attempt a history and opens a fresh socket.
    # Pretending otherwise would be the flattened-transcript defect in
    # another costume.
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


def transport_for(url, profile=None, transport=None):
    """
    The transport a target WOULD be reached by, resolved as the adapter does.

    For the telemetry, which has to record how the campaign reached the
    target and not merely what was typed: a `--target-profile websocket` or a
    `ws://` URL sets no flag, so reading the flag would have left the trail
    of every socket campaign saying nothing.

    One function rather than a second copy of the precedence -- the reason
    the PyRIT bridge reads `stats.STATES` and `label.py` reads
    `split_sets.imposed_set()`.
    """
    from config import HTTP_TARGET

    settings = TARGET_PROFILES.get(profile, {})
    return resolve_transport(url, transport, settings.get("transport"),
                             HTTP_TARGET["transport"])


def probe_target(url, headers=None, body=None, response_path=None, timeout=None,
           profile=None, show=print, transport=None):
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
    transport_final = resolve_transport(url, transport,
                                       settings.get("transport"),
                                       HTTP_TARGET["transport"])
    show(f"Transport: {transport_final} — "
         f"{TRANSPORTS[transport_final]}")
    show(f"Body     : {json.dumps(corps_final, ensure_ascii=False)}")
    show(f"Path     : {chemin_final}")
    if transport_final == GET_QUERY:
        # Said BEFORE the campaign, because a payload refused mid-campaign is
        # an attempt that never happened: an operator should know how much
        # room a payload has before spending a mandate on finding out.
        limit = HTTP_TARGET["url_limit"] or URL_LIMIT
        try:
            spare = limit - len(_query_url(url, _flat_fields(
                _inject(corps_final, ""), GET_QUERY)))
        except RuntimeError:
            # A nested body on a flat transport. The line is skipped rather
            # than allowed to raise mid-display: `build_http_target` below
            # refuses with the same reason, and reports it as FAILED with
            # every config line already shown.
            spare = None
        if spare is not None:
            show(f"URL room : {spare} characters for the payload, before "
                 f"percent-encoding (limit {limit}).")
            show("           Longer payloads are REFUSED, never truncated: "
                 "a server that cut one\n"
                 "           would have the target answer harmlessly and "
                 "the report call it safe.")
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
                                       chemin_final, timeout, profile=None,
                                       transport=transport_final)
    show(f"Sending  : {PROBE_MESSAGE}")
    try:
        reply = interroger(PROBE_MESSAGE)
    except RuntimeError as error:
        show(f"\nFAILED — {error}")
        _suggest(url, entetes_finaux, corps_final, timeout, show,
                 transport_final)
        return False

    show(f"Reply    : {reply[:300]}"
         + (" […]" if len(reply) > 300 else ""))
    if transport_final == WEBSOCKET:
        _how_the_socket_ended(getattr(interroger, "ended", None), show)
    show("\nWiring VALID: the target answers and the text reads correctly.")
    return True


def _how_the_socket_ended(ended, show):
    """
    Say whether the reply ended on a close frame or on the silence window.

    This is the one heuristic in the WebSocket client, and the one place it
    can be shown to an operator before it costs them a measurement: a reply
    that stopped on silence may have LOST A TAIL, and a tail holding the
    second half of a leak reads as a clean refusal. Said here, it is a knob
    to turn; discovered during a campaign, it is a false negative nobody
    sees.

    It takes the ending the probe's own call recorded. Asking the target a
    second time to find out would double what a verification leaves in a
    client's logs, and `--probe-target` promises exactly one message.
    """
    from config import HTTP_TARGET
    from targets import websocket as ws

    if ended == "close":
        show("Ends on  : the server's close frame — the reply is "
             "complete.")
    elif ended is not None:
        quiet = HTTP_TARGET["ws_quiet"] or ws.QUIET_SECONDS
        show(f"Ends on  : {quiet:g}s of SILENCE, not a close frame — so "
             f"a slower tail would be\n"
             f"           lost, and a cut reply reads as a clean refusal. "
             f"Raise TARGET_WS_QUIET\n"
             f"           if the reply above looks truncated.")


def _suggest(url, headers, body, timeout, show, transport=JSON_POST):
    """
    Relit la réponse brute pour proposer un path qui mène à du texte.

    Through `_raw_reply`, so the suggestion reaches the target the same way
    the campaign does. It used to POST JSON unconditionally: against a GET or
    a WebSocket endpoint it would have failed for its own reasons and the
    operator would have lost the most useful diagnosis in this file.
    """
    from config import HTTP_TARGET

    try:
        brut, _, _ = _raw_reply(transport, url, headers,
                                _inject(body, PROBE_MESSAGE), timeout or 60,
                                HTTP_TARGET["ws_quiet"],
                                HTTP_TARGET["url_limit"])
        data = json.loads(brut)
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

    # L'INDICE QUE LE CORPS EST FAUX LUI AUSSI, et il est AMBIGU -- ce qui
    # n'était pas dit, et c'était le défaut.
    #
    # L'intention était bonne : si la cible n'a jamais reçu le message,
    # corriger le seul chemin ne suffira pas, on relancerait, et la cible
    # répondrait toujours à côté en consommant du débit à chaque essai.
    #
    # Mais la version d'origine AFFIRMAIT « the target therefore did not
    # receive it ». Reproduit contre Ollama le 2026-11-20, corps correct et
    # chemin faux : la cible répond « Oui, je suis là pour t'aider. Je vous
    # reçois bien » et le message envoyait quand même corriger TARGET_BODY.
    # Un chatbot RÉPOND à une question, il ne la répète pas : l'absence
    # d'écho est donc le cas NORMAL, et le garde criait faux sur un
    # branchement parfait. C'est la famille de défaut pour laquelle ce projet
    # a déjà SUPPRIMÉ un garde -- un garde qui crie faux apprend à être
    # ignoré -- et c'est du mauvais conseil, qui coûte plus que pas de
    # conseil du tout.
    #
    # Aucun test ne figeait ce message : il n'avait jamais été exercé sur un
    # corps CORRECT, seulement sur un corps faux, où il tombait juste.
    #
    # Il dit maintenant les deux lectures et donne au lecteur le critère
    # qu'il peut appliquer lui-même, car il est le seul à pouvoir : la
    # réponse ci-dessus répond-elle à la question posée ?
    extrait_envoye = PROBE_MESSAGE[:20]
    if not any(extrait_envoye in valeur for _, valeur in chemins):
        show("\nNote: none of these texts repeats the message that was sent."
             "\n  That is NORMAL for a chatbot — it answers a question, it "
             "does not echo it.\n  But it is also what you see when "
             "TARGET_BODY is wrong and the target never\n  received the "
             "message at all. The reply above decides: if it does not answer"
             "\n  what was asked, the body needs fixing too, not just the "
             "path.\n  Starting from a known shape: --target-profile "
             f"{', '.join(TARGET_PROFILES)}")
