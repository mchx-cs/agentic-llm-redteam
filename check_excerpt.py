"""
Checks the README's campaign excerpt against a campaign's real output.

**An excerpt is EVIDENCE.** The README shows a run against `demo` "cut down to
what matters", and the only acceptable difference between it and the tool's own
output is a CUT, marked `[…]`. Re-wrapping a console block by hand is exactly
where a word gets reordered or an apostrophe normalised without anyone
noticing — and this repository has already published a target's reply
*translated*, found on 2026-11-12, where the lesson was recorded as: a
translated piece of evidence is no longer evidence.

Run after regenerating the excerpt, against the log of the campaign it came
from:

    python main.py --target demo --report > run.log
    python check_excerpt.py run.log

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

    The first line is the shell prompt, which is ours and not output, so it is
    dropped rather than looked for in the log.
    """
    body = excerpt.split("\n", 1)[1] if "\n" in excerpt else ""
    return [piece for piece in squash(body).split(squash(CUT)) if piece]


def console_block(readme):
    """The excerpt, between its fences. Raises if the README has none."""
    if FENCE not in readme:
        raise ValueError(f"no {FENCE.strip()} block in the README")
    return readme.split(FENCE, 1)[1].split("\n```", 1)[0]


def check(readme, log):
    """
    Returns the fragments that are NOT in the log, in order.

    Empty means the excerpt is faithful: every word of it was printed by the
    run, and everything left out is marked as left out.
    """
    squashed = squash(log)
    return [piece for piece in fragments(console_block(readme))
            if piece not in squashed]


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
    if len(arguments) != 1:
        # Said in full rather than sliced out of the docstring: an
        # instruction that depends on a paragraph's POSITION prints the wrong
        # paragraph the day one is added, and says nothing about it.
        print("Checks the README's campaign excerpt against a run's own "
              "output.\n\n"
              "  python main.py --target demo --report > run.log\n"
              "  python check_excerpt.py run.log\n")
        return 2

    readme = pathlib.Path("README.md").read_text(encoding="utf-8")
    log = pathlib.Path(arguments[0]).read_text(encoding="utf-8",
                                               errors="replace")
    missing = check(readme, log)

    total = len(fragments(console_block(readme)))
    if not missing:
        print(f"{total} fragment(s) of the README excerpt, all printed by "
              f"that run.")
        return 0

    print(f"{len(missing)} of {total} fragment(s) are NOT in the run's "
          f"output.\n")
    for piece in missing:
        print(f"NOT PRINTED: {piece[:120]}")
        detail = _where(piece, log)
        print(detail if detail else "  (nothing close in the log at all)")
        print()
    print("An excerpt is evidence: either quote what the run printed, or mark "
          f"the cut with {CUT}.")
    return 1


if __name__ == "__main__":
    write_in_utf8()
    sys.exit(main())
