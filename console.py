"""
Where this tool WRITES — and why one line deserved its own module.

Windows gives a REDIRECTED stdout the locale codec (cp1252 on this machine),
not UTF-8. So `python main.py --target … > campaign.log` encodes every
`print` through cp1252, and the first character a target writes outside that
codec — an emoji, an arrow, a check mark, a Chinese word, half of garak's
`encoding` payloads — raises `UnicodeEncodeError` from inside `print`.

**That kills a campaign, and it kills it at the worst moment.** The attempt
has been sent, the client's throughput has been spent, and what dies is the
run rather than the request. It happened for real on 2026-11-19, mid-campaign,
several minutes into local inference, on a measurement redirected to a file.

Redirecting to a file is not an edge case here: it is how every long
measurement in this project is run, and how an operator keeps a campaign's
output on an engagement. So this is a condition of running, not a nicety.

**What the fallback does, and why it is acceptable.** `errors="replace"` is a
last guard — UTF-8 encodes every string except a lone surrogate, which only
arrives from bytes decoded with `surrogateescape` — and where it fires it
shows `?` instead of a character. On a security tool that alteration has to be
named: **the terminal is a VIEW, not the record.** The record is the audit
trail (JSONL, written UTF-8 as it goes) and `result.json`. Losing a glyph on
screen costs nothing; losing the campaign costs the engagement.

**It is called by the ENTRY POINTS, never on import**, for the same reason the
budget is armed by the orchestrator rather than by `llm_client`: importing a
module must not reconfigure the interpreter's streams underneath whoever
imported it — `pytest` included, whose captured stdout is not a real stream.
"""

import sys


def write_in_utf8():
    """
    Makes this process's output UTF-8, whether it goes to a console or a file.

    Inert where it cannot apply: a stream replaced by a capture object (pytest)
    or by a plain file-like has no `reconfigure`, and a closed or detached
    stream raises. Neither is a reason to refuse to run, so both are ignored —
    this guard exists to let the work proceed, and failing because the guard
    failed would be the defect inverted.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):     # pragma: no cover
                pass
