"""
targets/websocket.py — A WebSocket client, on the standard library.

Plenty of chatbots are not reachable by a JSON POST at all: the browser opens
a WebSocket and the dialogue runs over it. Until now this adapter could not
aim at one, and the project recorded that gap with a reason attached — "that
one would add a dependency".

WHY IT DOES NOT, after all, and the argument is not "it was easy".

The single-dependency promise is load-bearing here: whoever clones this
repository installs `openai` and nothing else. PyRIT was made an EXTRA instead
of a dependency, so the precedent for an optional capability exists — but the
reason PyRIT is an extra does not transfer. PyRIT is alpha, it renamed its
central abstractions between two minor versions, and tracking it costs one
person's attention indefinitely. RFC 6455 was published in 2011 and has not
moved since: a frozen protocol does not rot the way an alpha library does,
which is the same asymmetry that made garak a SYNCED source for payloads —
payloads rot, a published algorithm does not.

And the decisive half: the framing is unit-testable with NO network and no
server. An extra cannot be exercised in continuous integration, where it is
not installed; these functions can, and are. So the choice is between a
dependency nobody tests in CI and ~150 lines that CI checks on every push.

WHAT THIS IS NOT. It is a one-shot client for a question-and-answer exchange:
connect, send one message, read the reply, close. It does not hold a
connection across attempts, and `targets/http.py` says why that matters for
multi-turn — a WebSocket chatbot that keeps the dialogue on the connection is
NOT supported, rather than faked.

No compression (`permessage-deflate` is never offered, so a server must not
use it), no subprotocol negotiation, no client certificates.
"""

import base64
import collections
import hashlib
import os
import socket
import ssl
import struct
import urllib.parse

# Opcodes, RFC 6455 §5.2.
CONTINUATION = 0x0
TEXT = 0x1
BINARY = 0x2
CLOSE = 0x8
PING = 0x9
PONG = 0xA

#: The magic string of RFC 6455 §1.3. The server appends it to the key we
#: send, hashes it, and returns the digest: that is what proves we reached a
#: WebSocket server and not a proxy that said 101 for its own reasons.
#:
#: WRITTEN FROM MEMORY FIRST, AND WRONG: the last group had been transposed to
#: `5AB0DC85B11C`. Every handshake would then have failed its own check, and
#: the message blames the TARGET -- "this is not a WebSocket server, most
#: likely a proxy" -- for our constant. Caught by asserting the digest the RFC
#: publishes for its own example, which is why that test quotes an external
#: value rather than our output.
GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

#: Bounds, because a declared length is the SERVER's claim and we are talking
#: to a system under test. A frame header can announce 2^63 bytes; believing
#: it would mean allocating it. A chatbot's reply is a few kilobytes.
MAX_MESSAGE = 1_000_000
MAX_FRAMES = 10_000

#: How long to wait for MORE after something has already arrived.
#:
#: A deliberate heuristic, and the only one in this file. A WebSocket chatbot
#: usually streams its answer as a series of small messages and sends no "I
#: have finished" marker — the connection simply stays open. SSE had `[DONE]`
#: and a body that ends; here nothing ends. So the reply is over when the
#: server closes (certain) or when it has been silent for this long (a guess).
#:
#: The cost is stated rather than hidden: a tail slower than this window is
#: LOST, and a lost tail is the silent-false-negative shape this project
#: hunts — a leak cut in half reads as a clean refusal. Hence two separate
#: delays. The FIRST message gets the full timeout, because a model thinking
#: before its first token is normal; only the gaps BETWEEN messages get this
#: short one. And `probe_target` reports which of the two ended the reply, so
#: an operator meets the question before the campaign rather than after.
QUIET_SECONDS = 2.0


Frame = collections.namedtuple("Frame", "fin opcode payload")

#: `frames` holds one entry per complete MESSAGE, beside the whole text. Both
#: are needed, and not for convenience: a socket that streams JSON objects
#: sends one per frame, so the stream reader wants them on separate lines,
#: while a plain-text bot sends its sentence in pieces where a newline
#: between them would corrupt it. The transport reports what arrived; the
#: reader decides how to read it.
Reply = collections.namedtuple("Reply", "text ended frames")


def mask(payload, key):
    """
    XOR a payload with a 4-byte key, as RFC 6455 §5.3 requires.

    Client-to-server frames MUST be masked — a server is entitled to close the
    connection on an unmasked one. Server-to-client frames must NOT be.

    Its own inverse, which is why one round-trip test covers both directions.
    """
    return bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))


def encode_frame(payload, opcode=TEXT, key=None):
    """
    One complete client frame: FIN set, masked, with the length encoded.

    The three length encodings are the part worth testing: under 126 inline,
    then a 2-byte big-endian count, then an 8-byte one. An attack payload is
    routinely over 126 bytes and occasionally over 65,535, so both boundaries
    are reached in ordinary use rather than in theory.
    """
    key = os.urandom(4) if key is None else key
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 1 << 16:
        header.append(0x80 | 126)
        header += struct.pack(">H", length)
    else:
        header.append(0x80 | 127)
        header += struct.pack(">Q", length)
    header += key
    return bytes(header) + mask(payload, key)


def parse_frame(buffer):
    """
    Take one frame off the front of `buffer`.

    Returns `(frame, rest)`, or `(None, buffer)` when the bytes in hand do not
    yet make a whole frame — a socket read gives whatever has arrived, not
    whatever we asked for, so an incomplete frame is the NORMAL case and must
    not raise.
    """
    if len(buffer) < 2:
        return None, buffer

    first, second = buffer[0], buffer[1]
    masked = bool(second & 0x80)
    length = second & 0x7F
    at = 2

    if length == 126:
        if len(buffer) < at + 2:
            return None, buffer
        length = struct.unpack(">H", buffer[at:at + 2])[0]
        at += 2
    elif length == 127:
        if len(buffer) < at + 8:
            return None, buffer
        length = struct.unpack(">Q", buffer[at:at + 8])[0]
        at += 8

    if length > MAX_MESSAGE:
        raise RuntimeError(
            f"WebSocket: the server announces a frame of {length} bytes, "
            f"over the {MAX_MESSAGE}-byte ceiling.\n"
            f"  A declared length is the SERVER's claim, and this one is "
            f"under test: we do not allocate it on request.")

    key = b""
    if masked:
        if len(buffer) < at + 4:
            return None, buffer
        key = buffer[at:at + 4]
        at += 4

    if len(buffer) < at + length:
        return None, buffer

    payload = buffer[at:at + length]
    return (Frame(bool(first & 0x80), first & 0x0F,
                  mask(payload, key) if masked else payload),
            buffer[at + length:])


def accept_token(key):
    """
    The `Sec-WebSocket-Accept` value a conforming server must return.

    Checked rather than ignored: a 101 with the wrong digest is not a
    WebSocket server, and carrying on would mean sending frames to something
    that will answer with anything at all.
    """
    digest = hashlib.sha1(key.encode("ascii") + GUID).digest()
    return base64.b64encode(digest).decode("ascii")


def handshake_request(url, headers=None, key=None):
    """
    The HTTP upgrade request, and the key whose echo we will verify.

    Returns `(bytes, key)`. The key is 16 random bytes in base64, per §4.1 —
    it is not a secret and proves nothing about us; it exists so the answer
    proves something about the server.
    """
    parts = urllib.parse.urlsplit(url)
    key = base64.b64encode(os.urandom(16)).decode("ascii") if key is None \
        else key
    target = parts.path or "/"
    if parts.query:
        target = f"{target}?{parts.query}"

    lines = [
        f"GET {target} HTTP/1.1",
        f"Host: {parts.netloc}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    # The operator's own headers last, so an `Origin` or a cookie they set is
    # not silently dropped -- several gateways reject a handshake without one.
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"), key


def read_handshake(received, key):
    """
    Check the server's answer to the upgrade, and return the leftover bytes.

    Those leftovers matter: a server may send its first frame in the same
    packet as the handshake, and dropping the tail of the buffer would lose
    the beginning of the reply -- a defect that would look like a slow target.
    """
    if b"\r\n\r\n" not in received:
        raise RuntimeError(
            "WebSocket: the server closed before finishing the handshake.\n"
            "  Check the URL's scheme (ws:// or wss://) and its path.")

    head, rest = received.split(b"\r\n\r\n", 1)
    text = head.decode("utf-8", "replace")
    status = text.splitlines()[0] if text.splitlines() else ""

    if " 101" not in status:
        raise RuntimeError(
            f"WebSocket: the server refused the upgrade.\n"
            f"  It answered: {status}\n"
            f"  101 Switching Protocols was expected. The usual causes:\n"
            f"    - the address is not the WebSocket endpoint (look for the "
            f"ws:// or wss:// URL\n"
            f"      in the browser's developer tools, Network tab, filter "
            f"WS);\n"
            f"    - the server requires an Origin header or a cookie: put "
            f"them in TARGET_HEADERS;\n"
            f"    - it requires a subprotocol, which this client does not "
            f"negotiate.")

    returned = ""
    for line in text.splitlines()[1:]:
        name, _, value = line.partition(":")
        if name.strip().lower() == "sec-websocket-accept":
            returned = value.strip()

    if returned != accept_token(key):
        raise RuntimeError(
            f"WebSocket: the server said 101 but its Sec-WebSocket-Accept "
            f"does not match.\n"
            f"  Received: {returned or 'nothing'}\n"
            f"  Expected: {accept_token(key)}\n"
            f"  So this is not a WebSocket server -- most likely a proxy "
            f"between us and it.")
    return rest


def collect(frames, ended):
    """
    Glue the frames of a reply into one text.

    TEXT and CONTINUATION carry the answer; a BINARY frame from a chatbot is
    not text and is left out rather than decoded into mojibake. Control frames
    (ping, pong, close) are not content either.

    Grouped by FIN, because a MESSAGE is what a reader cares about and a
    message may arrive in several frames.

    Decoding is `replace`: a reply cut at the quiet window can end inside a
    multi-byte character, and losing one glyph beats losing the evidence.
    """
    messages, current = [], []
    for frame in frames:
        if frame.opcode not in (TEXT, CONTINUATION):
            continue
        current.append(frame.payload)
        if frame.fin:
            messages.append(b"".join(current).decode("utf-8", "replace"))
            current = []
    if current:
        # A message whose final frame never came: kept rather than dropped,
        # since a reply cut at the silence window ends exactly like this and
        # its first half is still evidence.
        messages.append(b"".join(current).decode("utf-8", "replace"))
    return Reply("".join(messages), ended, messages)


def ask_over_websocket(url, text, headers=None, timeout=60.0,
                       quiet=QUIET_SECONDS):
    """
    Send one message over a WebSocket and return `Reply(text, ended)`.

    `ended` is "close" when the server closed the exchange itself, and
    "quiet" when we stopped on the silence window -- which is a guess, so the
    caller is given the means to say so.
    """
    parts = urllib.parse.urlsplit(url)
    secure = parts.scheme == "wss"
    port = parts.port or (443 if secure else 80)
    host = parts.hostname or ""

    try:
        connection = socket.create_connection((host, port), timeout=timeout)
    except OSError as error:
        raise RuntimeError(
            f"WebSocket {url}: unreachable ({error}).\n"
            f"  Check the URL, the network, and that the target is up."
        ) from error

    try:
        if secure:
            connection = ssl.create_default_context().wrap_socket(
                connection, server_hostname=host)

        request, key = handshake_request(url, headers)
        connection.sendall(request)

        # Read until the end of the headers, keeping whatever came after.
        received = b""
        while b"\r\n\r\n" not in received:
            chunk = connection.recv(4096)
            if not chunk:
                break
            received += chunk
        buffer = read_handshake(received, key)

        connection.sendall(encode_frame(text.encode("utf-8"), TEXT))

        frames, ended, held = [], "quiet", 0
        # Bounded, like every loop in this project: a server streaming empty
        # frames must not be able to keep a campaign running for ever.
        for _ in range(MAX_FRAMES):
            frame, buffer = parse_frame(buffer)
            if frame is None:
                # The first wait is the full timeout -- a model thinking
                # before its first token is normal. Afterwards, the short
                # window: see QUIET_SECONDS.
                connection.settimeout(timeout if not frames else quiet)
                try:
                    chunk = connection.recv(4096)
                except (socket.timeout, TimeoutError):
                    break
                except OSError:
                    break
                if not chunk:
                    ended = "close"
                    break
                buffer += chunk
                continue

            if frame.opcode == CLOSE:
                ended = "close"
                break
            if frame.opcode == PING:
                # Answering a ping is not politeness: a server is entitled to
                # close the connection when its ping goes unanswered, and the
                # reply would be lost mid-stream.
                connection.sendall(encode_frame(frame.payload, PONG))
                continue
            if frame.opcode == PONG:
                continue
            frames.append(frame)
            # A running total, not a sum over the list each time: bounded at
            # MAX_FRAMES, recomputing would be quadratic for no reason.
            held += len(frame.payload)
            if held > MAX_MESSAGE:
                break
    finally:
        try:
            connection.close()
        except OSError:                                   # pragma: no cover
            pass

    if not frames:
        raise RuntimeError(
            f"WebSocket {url}: connected, sent, and received nothing.\n"
            f"  The handshake worked, so the address is right. The usual "
            f"causes:\n"
            f"    - the server expects a different frame SHAPE (many expect "
            f"JSON, a few a bare\n"
            f"      sentence): check TARGET_BODY;\n"
            f"    - it waits for a subscription or an authentication frame "
            f"first, which this\n"
            f"      client does not send;\n"
            f"    - it answered more slowly than the {timeout:g}s timeout.")

    return collect(frames, ended)
