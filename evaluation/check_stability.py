"""
evaluation/check_stability.py — Did an edit DO anything, or is this case just
unstable?

THE QUESTION THIS ANSWERS, and no other tool in the project answers it.

The judge is not deterministic even at temperature 0: measured on 2026-11-10,
one case gave `[True, True, True, True, False]`, and `seed` changed nothing —
`gpt-oss-120b` is a mixture of experts, so routing and batching vary. The
project drew two consequences at the time, one for the MEASUREMENT (one case
in ~57 can flip, so ±2 points is noise) and one for campaign VERDICTS (hence
`judge_by_vote`).

It never drew the third, and 2026-11-18 showed why it matters. Three dev runs
around one prompt edit moved four cases in and out of the error list while the
totals barely budged, and three conclusions drawn from that movement turned
out to be WRONG:

  * "A08 is fixed" — it is stable and wrong five times out of five; the fix
    had done nothing and the run that showed it passing was a draw;
  * "D18-2 is a new regression" — it is stable and correct; its appearance was
    a draw;
  * "the seam is fixed" — the case is UNSTABLE, 3 failures in 5. It failed
    before and it fails still.

A single run cannot tell a repaired case from a lucky one. This module judges
a NAMED FEW several times and says which verdicts are stable.

WHY NOT JUST VOTE IN THE EVALUATION. Because they answer different questions.
`evaluate_judge` calls `judge()` directly and deliberately does not vote: it
must measure the judge AS IT IS, and voting there would mask the instability
instead of revealing it — and triple the cost of every evaluation. This module
asks something else: is THIS case's verdict a property of the case or of the
draw. The instruments stay separate, like `tests/` and `evaluation/`.

WHAT IT COSTS. `ROUNDS` judgements per case named, and nothing else: a handful
of cases is a handful of calls. That is what makes it usable after every edit,
where a full dev run is not.

WHAT IT DOES NOT SAY. Ten rounds bound a flip rate loosely: a case correct
10/10 could still fail one time in four. `stats.wilson_interval` is printed
for exactly that reason — "stable" here means "did not flip in ten", never
"never flips".

AND WHY TEN RATHER THAN FIVE. Five was the first default, and it was measured
insufficient the next day: three 5-round verdicts were overturned, and two of
them had already been written down as conclusions. See `ROUNDS` below.
"""

import argparse
import json
from pathlib import Path

import stats
from agents.judge import judge, judge_conversation
from console import write_in_utf8

CORPUS_FILE = Path(__file__).with_name("labelled_exchanges.json")

# Raised from 5 to 10 on 2026-11-19, because five was MEASURED insufficient
# one day after it was chosen -- and by this module's own output.
#
# Three 5-round verdicts were overturned within two days:
#   * `C-demo3-01-2-mono` gave 3/5 wrong, then 0/5 wrong, with nothing changed
#     between the two samples;
#   * `A08` was read as "stable, WRONG" on 5/5 and the echo exemption declared
#     to have done nothing. Pooled over fifteen rounds it is 9/15 -- unstable,
#     and that conclusion was an over-read;
#   * `P11` was read as "UNSTABLE (3/5)" and a third exemption refused as
#     "tuning on noise". Over ten rounds it is 10/10 wrong: a stable, real
#     false positive, so the refusal rested on a belief the measurement
#     contradicts.
#
# The arithmetic says why. A case that flips 30% of the time shows no flip at
# all in five rounds about one time in six (0.7^5 = 17%), so "stable" at five
# is a coin's own verdict on itself. At ten it is 2.8%.
#
# The cost doubles and that is accepted: this module exists to stop an edit
# being credited for a draw, and at five rounds it was doing the opposite
# often enough to produce three wrong conclusions. Correct first.
#
# What has NOT changed: ten rounds still bound loosely, and the Wilson
# interval printed beside each line is what says so. "Stable" means "did not
# flip in ten", never "never flips" -- 10/10 correct still allows a real flip
# rate of 28%.
ROUNDS = 10


# The SECOND copy of this predicate until 2026-11-24. Read from the module
# that owns the corpus's shape: two definitions of one rule drift, and this
# one decides which INSTRUCTION an entry is judged by.
from evaluation.label import is_conversation  # noqa: E402,F401


def judge_entry(entry):
    """One verdict on one entry, in the format the entry declares."""
    if is_conversation(entry):
        return judge_conversation(entry["turns"])
    if entry.get("turns"):
        # A single exchange stored as `turns`: judged single-turn, because
        # that is what it is. Passing it to the conversation path would judge
        # it with an addendum written for several turns.
        return judge(entry["turns"][0]["content"], entry["turns"][1]["content"])
    return judge(entry["payload"], entry["reply"])


def read_corpus(path=CORPUS_FILE):
    return {e["id"]: e for e in
            json.loads(Path(path).read_text(encoding="utf-8"))["exchanges"]}


def reading(votes, expected, rounds):
    """
    What the votes support, naming the SAMPLE and never the case.

    Three outcomes, and none of them says "stable". That word was in the first
    two versions and it was wrong twice in one day: `A08` read "stable, WRONG"
    on 5/5 is 9/15 pooled, and `P11` read "stable, WRONG" on 10/10 is 31/40.
    Raising the rounds was the right direction and did not help, because the
    defect was in the WORD -- a line saying "stable, correct" beside
    "Wilson 72%-100%" asserts stability and admits a 28% flip rate at once,
    and a reader keeps the word.

    So the bound is IN the label. No number of rounds supports "stable", and
    the only honest claim is about what was observed and what it allows.
    """
    wrong = sum(1 for v in votes if v is not expected)
    high = stats.wilson_interval(wrong, rounds)[1]
    low = stats.wilson_interval(wrong, rounds)[0]
    if wrong == 0:
        return f"no flip in {rounds} (<={high:.0%})", wrong
    if wrong == rounds:
        return f"wrong every time (>={low:.0%})", wrong
    # The bound matters MOST here, and the first version left it out: a
    # 5/10 split allows anything from 24% to 76%, so the fraction
    # alone invites reading it as "about half". Found by my own test
    # demanding a percentage in every reading.
    return f"FLIPS ({wrong}/{rounds}, {low:.0%}-{high:.0%})", wrong


def check(ids, rounds=ROUNDS, corpus=None, show=print, judge_one=None):
    """
    Judge each named entry `rounds` times and report what is stable.

    `judge_one` is a parameter rather than an import so the logic can be
    tested with a simulated judge of known behaviour — the same reason
    `verify_by_replay` takes its target and its judge.
    """
    corpus = corpus if corpus is not None else read_corpus()
    judge_one = judge_one or judge_entry

    show(f"{rounds} judgement(s) of each case, to tell a stable verdict from "
         f"a coin.")
    show("A case that answers differently to the same question is the judge's "
         "non-determinism,")
    show("measured on 2026-11-10: no prompt edit should be credited or blamed "
         "for it.\n")

    results = {}
    for identifier in ids:
        entry = corpus.get(identifier)
        if entry is None:
            show(f"  {identifier:26s} ABSENT from the corpus")
            continue
        votes = [judge_one(entry)["reussi"] for _ in range(rounds)]
        verdict, wrong = reading(votes, entry["expected"], rounds)
        marks = "".join("." if v is entry["expected"] else "X" for v in votes)
        low, high = stats.wilson_interval(rounds - wrong, rounds)
        show(f"  {identifier:26s} label={str(entry['expected']):5s} "
             f"{marks:8s} {verdict:24s} "
             f"correct {rounds - wrong}/{rounds} "
             f"(Wilson {low:.0%}–{high:.0%})")
        results[identifier] = {"votes": votes, "wrong": wrong,
                               "reading": verdict}

    unstable = [i for i, r in results.items() if "FLIPS" in r["reading"]]
    if unstable:
        show(f"\n/!\\ {len(unstable)} case(s) seen flipping: "
             f"{', '.join(unstable)}")
        show("    A run that shows one of these passing proves nothing, and a "
             "run that shows it")
        show("    failing proves nothing either. Attribute neither to an "
             "edit.")
    return results


def main(arguments=None):
    parser = argparse.ArgumentParser(
        description="Judge named corpus entries several times, to tell a "
                    "stable verdict from the judge's non-determinism.")
    parser.add_argument("ids", nargs="+", metavar="ID",
                        help="corpus entry identifiers (E08, P11, …)")
    parser.add_argument("--rounds", type=int, default=ROUNDS,
                        help=f"judgements per case (default {ROUNDS})")
    arguments = parser.parse_args(arguments)
    check(arguments.ids, rounds=arguments.rounds)
    return 0


if __name__ == "__main__":
    write_in_utf8()
    main()
