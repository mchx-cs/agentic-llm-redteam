"""
Checks the README's console excerpts against the real output they came from.

**An excerpt is EVIDENCE.** The README shows a run against `demo` "cut down to
what matters", and the only acceptable difference between it and the tool's own
output is a CUT, marked `[…]`. Re-wrapping a console block by hand is exactly
where a word gets reordered or an apostrophe normalised without anyone
noticing — and this repository has already published a target's reply
*translated*, found on 2026-11-12, where the lesson was recorded as: a
translated piece of evidence is no longer evidence.

Run after regenerating an excerpt, against the logs the excerpts came from.
The README has TWO console blocks and each needs its own:

    python main.py --target demo --report > run.log
    TARGET_BODY='{"model":"llama3.2","prompt":"{message}","stream":false}' \\
        python main.py --target http://localhost:11434/api/generate \\
        --probe-target > probe.log
    python check_excerpt.py run.log probe.log

**It checked only the FIRST block until 2026-11-20**, and the second one is
where a defect was found -- by reproducing it by hand, since nothing else
would have. An excerpt no guard covers is the defect itself, so every block
now needs a log, and a block no log covers FAILS rather than passing in
silence.

**It is a command and not a test, for a reason.** A test would need the log
committed, and the log holds the complete payloads and the target's complete
replies — which is the very thing `--abridge` exists to keep out of a public
repository. So the check needs a file the repository deliberately does not
keep, and it runs by hand, like `check_rename_damage.py`.

Method: whitespace is OURS (the wrapping, the column alignment), the words are
the TOOL's. So both sides are squashed to a whitespace-free string, the excerpt
is split on the cut marker, and every remaining fragment must appear in the
log. That catches a reordering, a changed character and an unmarked omission
alike, while allowing any amount of re-wrapping.
"""

import pathlib
import re
import sys

from console import write_in_utf8

CUT = "[…]"
FENCE = "```console\n"


def squash(text):
    """Drops every whitespace character: only the words are the tool's."""
    return re.sub(r"\s+", "", text)


def fragments(excerpt):
    """
    The excerpt's verbatim pieces, in order.

    The shell prompt is OURS and not output, so it is dropped rather than
    looked for in the log -- and dropped WHOLE, continuation lines included.

    Only the first line was dropped until 2026-11-20, so a command continued
    with a backslash had its tail hunted in the target's output, where it has
    no reason to be. Found by needing a two-line command: the probe excerpt
    sets TARGET_BODY in front of it, and one line would be unreadable.
    """
    lines = excerpt.split("\n")
    start = 0
    if lines and lines[0].lstrip().startswith("$"):
        start = 1
        while start < len(lines) and lines[start - 1].rstrip().endswith("\\"):
            start += 1
    body = "\n".join(lines[start:])
    return [piece for piece in squash(body).split(squash(CUT)) if piece]


def console_block(readme, which=0):
    """One excerpt, between its fences. Raises if the README has none."""
    found = console_blocks(readme)
    return found[which]


def console_blocks(readme):
    """
    EVERY console excerpt, in the order the README shows them.

    There are two: the campaign, and the `--probe-target` wiring check. The
    second had never been checked by anything, which is how its warning came
    to claim "the target therefore did not receive it" about a target that
    plainly had.
    """
    if FENCE not in readme:
        raise ValueError(f"no {FENCE.strip()} block in the README")
    return [piece.split("\n```", 1)[0]
            for piece in readme.split(FENCE)[1:]]


def check(readme, log, which=0):
    """
    Returns the fragments of one excerpt that are NOT in the log, in order.

    Empty means the excerpt is faithful: every word of it was printed by the
    run, and everything left out is marked as left out.
    """
    squashed = squash(log)
    return [piece for piece in fragments(console_block(readme, which))
            if piece not in squashed]


def best_log(pieces, logs):
    """
    Which log an excerpt came from, and what is missing from it.

    Chosen by the log that covers the MOST fragments rather than by the order
    the arguments came in: an operator passing two logs should not have to
    remember which excerpt is which, and a wrong pairing would report a
    divergence against output the excerpt was never cut from.

    Returns `(name, missing)`, with `missing` holding every fragment when no
    log covers a single one -- which is a block nobody has verified, and the
    exact state this guard was extended to end.
    """
    best, missing = None, list(pieces)
    for name, text in logs.items():
        squashed = squash(text)
        absent = [piece for piece in pieces if piece not in squashed]
        if best is None or len(absent) < len(missing):
            best, missing = name, absent
    return best, missing


def _where(piece, log):
    """
    How far a fragment matches, so a divergence can be read and not hunted.

    By the LONGEST PREFIX the log contains, never by a fixed-length anchor:
    the first version anchored on the first 25 characters, which fails
    precisely when the divergence is inside them — a changed apostrophe three
    words in, which is the real case that prompted all this. It then reported
    "nothing close in the log at all" about a fragment that matched almost
    entirely.
    """
    squashed = squash(log)
    length = 0
    while length < len(piece) and piece[:length + 1] in squashed:
        length += 1
    if length == 0:
        return None
    start = squashed.find(piece[:length])
    return (f"  diverges after {length} character(s)\n"
            f"    README : …{piece[max(0, length - 30):length]}"
            f" >>> {piece[length:length + 40]}\n"
            f"    the run: …{squashed[start + max(0, length - 30):start + length]}"
            f" >>> {squashed[start + length:start + length + 40]}")


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments:
        # Said in full rather than sliced out of the docstring: an
        # instruction that depends on a paragraph's POSITION prints the wrong
        # paragraph the day one is added, and says nothing about it.
        print("Checks the README's console excerpts against the real output "
              "they came from.\n\n"
              "  python main.py --target demo --report > run.log\n"
              "  python main.py --target http://localhost:11434/api/generate"
              " --probe-target > probe.log\n"
              "  python check_excerpt.py run.log probe.log\n\n"
              "One log per console block in the README; a block no log "
              "covers is reported\nas unverified, because an excerpt nobody "
              "checks is the defect.\n")
        return 2

    readme = pathlib.Path("README.md").read_text(encoding="utf-8")
    logs = {name: pathlib.Path(name).read_text(encoding="utf-8",
                                               errors="replace")
            for name in arguments}

    blocks = console_blocks(readme)
    failed = False
    for which, block in enumerate(blocks, start=1):
        pieces = fragments(block)
        name, missing = best_log(pieces, logs)
        first = (block.split("\n", 1)[0] or "?").strip()

        if not missing:
            print(f"Block {which}/{len(blocks)} ({first[:60]}): "
                  f"{len(pieces)} fragment(s), all printed by {name}.")
            continue

        failed = True
        print(f"Block {which}/{len(blocks)} ({first[:60]}): "
              f"{len(missing)} of {len(pieces)} fragment(s) are NOT in "
              f"{name}.")
        if len(missing) == len(pieces):
            # BOTH readings, never a guess between them. Telling them apart
            # would need a threshold on how much of a fragment matched, and
            # with a one-fragment excerpt there is nothing to threshold --
            # which is how a first version here reported "unverified" about
            # an excerpt that was simply wrong. The divergence printed below
            # settles it for the reader in one glance.
            print("  NOTHING of this block matched: either the log of the "
                  "command it shows was\n  not passed -- an excerpt nobody "
                  "checks is the defect this guard was extended\n  to end -- "
                  "or the excerpt does not come from that output at all.")
        print()
        for piece in missing:
            print(f"NOT PRINTED: {piece[:120]}")
            detail = _where(piece, logs[name])
            print(detail if detail else "  (nothing close in that log at all)")
            print()

    if failed:
        print("An excerpt is evidence: either quote what the run printed, or "
              f"mark the cut with {CUT}.")
    return 1 if failed else 0


if __name__ == "__main__":
    write_in_utf8()
    sys.exit(main())
