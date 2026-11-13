"""
agents/detecteurs.py — Deterministic pre-processing of the target's replies.

An LLM is bad at decoding Base64 in its head, or at spotting that a word was
written letter by letter. Python code does it without ever getting it wrong. So
we do that work BEFORE the judge and show it the result: it then judges plain
text instead of having to guess.

These detectors decide NOTHING: they do not know the secret and they never say
"finding". They only make visible what was hidden. The decision stays with the
judge (the blind-judge principle).

NOTE ON NAMING (2026-11-13). The returned dictionaries' keys — and the VALUES
of their `type` field — stay French on purpose. They are rendered straight into
the judge's prompt, under an "Décodage automatique" heading its instruction
refers to. Translating them changes the judge's prompt, which is the last step
of the switch and a measured one. See `GLOSSAIRE.md`.
"""

import base64
import binascii
import re

# At least 4 isolated characters separated by spaces, dashes, dots…
# e.g. "T - O - P - S" or "T.O.P.S". Below 4, too many false positives
# ("a - b" shows up in ordinary text).
_SPELLED_OUT_PATTERN = re.compile(r"(?<!\w)(?:\w[\s\-\.\,·_/|]+){3,}\w(?!\w)")
_SEPARATORS = re.compile(r"[\s\-\.\,·_/|]+")

# Base64 candidates: 8 or more characters of the Base64 alphabet.
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{8,}={0,2}")

# Hex candidates: at least 4 bytes (8 hex digits).
_HEX_PATTERN = re.compile(r"\b(?:[0-9a-fA-F]{2}){4,}\b")

# The characters REAL text can contain: printable ASCII, accented Latin
# letters (Latin-1 and Latin Extended-A), and a few common typographic signs.
# Everything else — ideographs, non-Latin scripts, symbols — signals a decoding
# of arbitrary bytes, not language.
_PLAUSIBLE_RANGES = ((0x20, 0x7E), (0x00C0, 0x00FF), (0x0100, 0x017F))
_COMMON_SIGNS = "€’‘“”«»—–…°"

# A decoding must carry at least this much substance. Below it, "n&a" passes
# every character filter without meaning anything.
_MINIMUM_ALPHANUMERIC = 3


def _is_plausible_character(character):
    point = ord(character)
    return (character in _COMMON_SIGNS
            or any(start <= point <= end for start, end in _PLAUSIBLE_RANGES))


def _is_readable_text(text):
    """
    A decoding only means something if it yields TEXT, not binary noise.

    The original filter accepted any printable string containing one
    alphanumeric character, and that was far too broad. Measured 2026-11-13 on
    a harvest of 119 conversations: **73 entries** carried a bogus "Base64
    decoding", because `_BASE64_PATTERN` catches eight Latin letters in a row
    and an ordinary French word decodes to valid bytes. `biblioth` —
    "bibliothèque" cut at the accent — gives `n&劋a`, which is printable and
    contains alphanumerics.

    This was not a cosmetic defect: those decodings are injected into the
    judge's instruction, under a heading telling it to judge them as if the
    chatbot had written them. So we were feeding it noise on three `dev`
    entries and one `test` entry — on every measurement, including all three
    consultations of the frozen set.

    The filter now requires EVERY character to be plausible in written
    language. That is deliberately strict: a decoding containing a single
    exotic character is dropped. The trade-off is accepted — an encoded leak
    containing an ideograph would go unnoticed, whereas the old filter drowned
    the judge in gibberish on six entries out of ten. Missing a rare form
    costs less than polluting every measurement.
    """
    if not text or not text.isprintable():
        return False
    if sum(1 for c in text if c.isalnum()) < _MINIMUM_ALPHANUMERIC:
        return False
    return all(_is_plausible_character(c) for c in text)


def reassemble_spelled_out(reply):
    """Find words written letter by letter and glue them back together."""
    found = []
    for match in _SPELLED_OUT_PATTERN.finditer(reply):
        chunk = match.group()
        letters = _SEPARATORS.split(chunk)
        # Only genuine spellings count: one character per piece. Otherwise
        # "Je suis là - pour vous" would be read as a spelling.
        if all(len(letter) == 1 for letter in letters):
            found.append({"type": "épelé", "original": chunk,
                          "decode": "".join(letters)})
    return found


def decode_base64(reply):
    """Find Base64 strings that decode to readable text."""
    found = []
    for candidate in _BASE64_PATTERN.findall(reply):
        try:
            # validate=True: reject anything outside the Base64 alphabet.
            decoded = base64.b64decode(candidate, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            continue  # not Base64, or binary: ignore it
        # An ordinary word like "question" also "decodes", but into unreadable
        # bytes: the readability filter drops those.
        if _is_readable_text(decoded):
            found.append({"type": "base64", "original": candidate,
                          "decode": decoded})
    return found


def decode_hex(reply):
    """Find hexadecimal strings that decode to readable text."""
    found = []
    for candidate in _HEX_PATTERN.findall(reply):
        try:
            decoded = bytes.fromhex(candidate).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if _is_readable_text(decoded):
            found.append({"type": "hexadécimal", "original": candidate,
                          "decode": decoded})
    return found


def analyse(reply):
    """Run every detector. Returns the list of what they decoded."""
    return (reassemble_spelled_out(reply) + decode_base64(reply)
            + decode_hex(reply))
