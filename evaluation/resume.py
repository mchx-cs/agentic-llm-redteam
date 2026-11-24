"""
evaluation/resume.py — Lets an interrupted evaluation pick up where it stopped.

A full consultation of the 209-entry corpus is ~301,000 tokens and several
hundred sequential calls. A failure on call 150 of 154 loses the run: not a
money problem at the listed rates, but a run to redo, and the kind of thing
that happens when a network blips.

So each verdict is appended to a JSONL and flushed, exactly as the audit trail
is — the shape the project already trusts, for the same reason: if the thing
dies, what already happened survives.

THE DECISION THAT SHAPES EVERYTHING ELSE: a cache is for RESUMING an
interrupted run, never for REPEATING a finished one.

The judge is not deterministic, even at temperature 0 — measured on this
project on 2026-11-10, where E10-b gave [True, True, True, True, False] and
`seed` changed nothing. A cache that survived a completed run would make a
rerun reproduce its predecessor instead of resampling, and the variance the
project went to the trouble of measuring would silently disappear from every
figure after the first.

Hence `discard()` on a successful finish. Resuming is a repair; repeating is a
new measurement, and it has to cost what a new measurement costs.

WHAT INVALIDATES AN ENTRY, and why each one matters:

- **the judge** (`profile/model`). Resuming across a change of judge would
  blend two models in one figure. The project refuses that blending for
  defence levels, for formats and for languages; it is no different here.
- **the instruction's language**. Same argument: `--language en` and
  `--language fr` are the two arms of a comparison, and mixing them would
  destroy it.
- **the QUESTION's digest**. If the exchange's text changed — a corpus edit,
  a relabelled entry re-harvested — the cached verdict is about something
  else. The digest catches that; the entry's id alone would not.
- **the INSTRUCTION's digest**, added 2026-11-24. "A verdict is a function of
  the instruction and the question" was written here from the first day, and
  only the question half was keyed on. So a run interrupted before a prompt
  correction and resumed after it would have served verdicts measured on the
  OLD instruction, silently, inside a figure presented as one measurement.
  Nothing stale was ever served — checked rather than assumed before the
  re-measurement of 2026-11-24, where no cache existed — but the gap was
  real, and the correction of that day (7,592 → 8,821 characters) is exactly
  the event that would have triggered it.

  It is keyed PER ENTRY and not per run, because the instruction depends on
  the format: a single-turn entry is judged by the base, a conversation by
  base plus addendum. Keying the whole run on one digest would re-judge 121
  intact single-turn verdicts whenever only the addendum moved.

A label change does NOT invalidate anything, deliberately: the verdict is
about the exchange, not about what the author decided it means. Re-judging
after a relabelling would cost quota for a verdict that cannot differ.
"""

import hashlib
import json
from pathlib import Path

FOLDER = Path(__file__).parent


def path_for(dataset):
    """The cache for one set. Gitignored: it is a working file."""
    return FOLDER / f".verdicts-{dataset}.jsonl"


def digest(question):
    """What the judge was actually asked, fingerprinted."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]


class Cache:
    """
    Verdicts already obtained for this run.

    Deliberately a small class rather than two loose functions: the identity
    that makes a cached verdict valid (judge + language) has to be decided
    once, at the top, and then carried — passing it to every call is how one
    call ends up forgetting it.
    """

    def __init__(self, dataset, judge, language):
        self.path = path_for(dataset)
        self.judge = judge
        self.language = language
        self._done = {}
        self._load()

    @staticmethod
    def _key(identifier, question, instruction):
        """
        What makes a cached verdict THIS verdict.

        The instruction is digested rather than stored: a row carrying nine
        thousand characters per verdict would make the working file unusable,
        and only equality is ever asked of it.
        """
        return (identifier, digest(question), digest(instruction))

    def _load(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # A half-written last line is exactly what an interruption
                # leaves behind. Skipping it is the point of the format.
                continue
            if row.get("judge") != self.judge:
                continue
            if row.get("language") != self.language:
                continue
            # A row written before the instruction was keyed on carries no
            # `instruction` field. It is DROPPED rather than trusted: its
            # verdict may have been measured on another instruction, and the
            # one thing this cache must never do is serve a stale verdict
            # into a figure. Dropping costs a re-judgement; trusting costs
            # the measurement.
            if "instruction" not in row:
                continue
            self._done[(row["id"], row["digest"],
                        row["instruction"])] = row["verdict"]

    def get(self, identifier, question, instruction):
        """The verdict already obtained for this exact question, or None."""
        return self._done.get(self._key(identifier, question, instruction))

    def put(self, identifier, question, verdict, instruction):
        """Records a verdict and FLUSHES: an interruption must keep it."""
        row = {"id": identifier, "digest": digest(question),
               "instruction": digest(instruction),
               "judge": self.judge, "language": self.language,
               "verdict": verdict}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
        self._done[self._key(identifier, question, instruction)] = verdict

    def discard(self):
        """
        Clears the cache once the run has finished.

        The run is over, so there is nothing to resume — and keeping it would
        turn the next invocation into a replay of this one rather than a fresh
        sample of a non-deterministic judge.
        """
        self.path.unlink(missing_ok=True)

    def __len__(self):
        return len(self._done)
