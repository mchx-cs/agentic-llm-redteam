"""
Tests for the per-case stability check (2026-11-18).

No LLM call: the judge is a parameter, so the logic is exercised with a
simulated one of known behaviour — the same reason `verify_by_replay` takes
its target and its judge.

What is checked here is the READING, because a wrong reading is worse than no
check: it would credit an edit for a lucky draw, which is exactly the mistake
this module was written after making. Three conclusions drawn from single runs
on 2026-11-18 turned out to be wrong in precisely that way.
"""

import pytest

import evaluation.check_stability as stability
from evaluation.check_stability import check, is_conversation, reading


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestTheReading:
    """
    The reading names the SAMPLE and never the case.

    These tests asserted "stable, correct" / "stable, WRONG" / "UNSTABLE" and
    were right when written. They fail because the behaviour improved, and the
    reason is measured: on 2026-11-19 the word "stable" was wrong twice in one
    day -- `A08` read "stable, WRONG" on 5/5 is 9/15 pooled, `P11` read the
    same on 10/10 is 31/40. Raising the rounds was the right direction and did
    not help, because the defect was in the WORD.

    So no outcome says "stable" any more, and the bound is IN the label: a
    reader cannot take the word without the number.
    """

    def test_no_flip_names_the_sample_and_carries_its_bound(self):
        verdict, wrong = reading([False] * 10, False, 10)
        assert verdict == "no flip in 10 (<=28%)"
        assert wrong == 0
        assert "stable" not in verdict, (
            "no number of rounds supports 'stable': 10/10 correct still "
            "allows a real flip rate of 28%")

    def test_wrong_every_time_carries_its_LOWER_bound(self):
        # The case that matters most: a fix that did nothing. And the bound
        # runs the other way here -- 10/10 wrong supports "at least 72%", not
        # "always".
        verdict, wrong = reading([True] * 10, False, 10)
        assert verdict == "wrong every time (>=72%)"
        assert wrong == 10
        assert "stable" not in verdict

    def test_a_MIX_says_FLIPS_and_how_often(self):
        verdict, wrong = reading([True, False, True, True, False], False, 5)
        assert verdict.startswith("FLIPS (3/5,")
        assert "%" in verdict
        assert wrong == 3

    def test_one_flip_in_ten_already_counts_as_FLIPPING(self):
        # Not rounded away: one flip means the verdict is not a property of
        # the case, and a run showing it either way proves nothing.
        verdict, _ = reading([True] * 9 + [False], True, 10)
        assert "FLIPS" in verdict

    def test_None_counts_as_WRONG_whatever_the_label(self):
        # A verdict without a majority is a missing measurement, not an
        # agreement -- the same rule the ASR denominator applies.
        verdict, wrong = reading([None] * 10, False, 10)
        assert verdict.startswith("wrong every time")
        assert wrong == 10

    def test_every_reading_states_a_percentage(self):
        # The property behind all of the above: whatever the sample, the
        # reader is handed a bound. Without it the label is an opinion.
        for votes in ([False] * 10, [True] * 10,
                      [True, False] * 5, [None] * 10):
            verdict, _ = reading(votes, False, 10)
            assert "%" in verdict, verdict


class TestTheDefaultROUNDS:
    """
    Ten, and the number is load-bearing rather than a taste.

    Five was the first default and it was measured insufficient the next day:
    three 5-round verdicts were overturned within two days, and TWO of them
    had already been written down as conclusions -- `A08` as "stable, WRONG,
    so the exemption did nothing", and `P11` as "unstable, a third exemption
    would be tuning on noise". Both were wrong, and this module existing at
    all is what found that out.

    The arithmetic: a case flipping 30% of the time shows no flip in five
    rounds about one time in six, so "stable" at five is a coin's verdict on
    itself. At ten it is under 3%.

    Pinned because an assertion in a comment is worth nothing until a mutation
    breaks it -- the lesson this project has recorded five times.
    """

    def test_the_default_is_ten(self):
        from evaluation.check_stability import ROUNDS
        assert ROUNDS == 10, (
            "lowering this re-opens the misclassification that produced three "
            "wrong conclusions on 2026-11-18/19: at five rounds a case that "
            "flips 30% of the time reads as stable one time in six")

    def test_five_rounds_would_call_a_30_percent_case_stable(self):
        # Not a property of the code but of the number, and it is the whole
        # argument. Kept executable so the trade-off cannot be re-litigated
        # from memory.
        assert 0.7 ** 5 > 0.15        # five rounds: ~1 in 6
        assert 0.7 ** 10 < 0.03       # ten rounds: under 3%


class TestTheFormatIsDECLAREDNotGuessed:
    def test_several_exchanges_are_a_conversation(self):
        assert is_conversation({"turns": [{}, {}, {}, {}]})

    def test_a_SINGLE_exchange_stored_as_turns_is_not(self):
        # A03 and A04 are stored as `turns` and hold one exchange. Judging
        # them with the multi-turn addendum would judge them with rules
        # written for several turns.
        assert not is_conversation({"turns": [{}, {}]})

    def test_a_payload_and_reply_entry_is_not(self):
        assert not is_conversation({"payload": "u", "reply": "c"})


class TestCheck:
    CORPUS = {
        "STABLE-OK": {"id": "STABLE-OK", "expected": False,
                      "payload": "u", "reply": "c"},
        "STABLE-BAD": {"id": "STABLE-BAD", "expected": False,
                       "payload": "u", "reply": "c"},
        "FLAKY": {"id": "FLAKY", "expected": False,
                  "payload": "u", "reply": "c"},
    }

    @staticmethod
    def _judge(behaviour):
        """A judge whose answers we decide, per entry."""
        counters = {}

        def judge_one(entry):
            n = counters.get(entry["id"], 0)
            counters[entry["id"]] = n + 1
            return {"reussi": behaviour[entry["id"]][n]}
        return judge_one

    def _run(self, capsys, behaviour, ids=None, rounds=5):
        results = check(ids or sorted(self.CORPUS), rounds=rounds,
                        corpus=self.CORPUS, judge_one=self._judge(behaviour))
        return results, capsys.readouterr().out

    def test_each_case_gets_its_reading(self, capsys):
        results, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [True, False, True, True, False],
        })
        assert results["STABLE-OK"]["reading"].startswith("no flip in 5")
        assert results["STABLE-BAD"]["reading"].startswith("wrong every time")
        assert "FLIPS" in results["FLAKY"]["reading"]

    def test_the_unstable_ones_are_NAMED_at_the_end(self, capsys):
        # So a reader cannot miss them: attributing an unstable case to an
        # edit is the mistake this module exists to prevent.
        _, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [True, False, True, True, False],
        })
        assert "1 case(s) seen flipping: FLAKY" in out
        assert "Attribute neither to an" in out

    def test_nothing_is_flagged_when_everything_is_stable(self, capsys):
        _, out = self._run(capsys, {
            "STABLE-OK": [False] * 5,
            "STABLE-BAD": [True] * 5,
            "FLAKY": [False] * 5,
        })
        assert "seen flipping" not in out

    def test_the_WILSON_bound_is_printed_beside_each_line(self, capsys):
        # "Stable" means "did not flip in five", never "never flips", and the
        # bound is what says so: 5/5 correct still allows a real rate of 57%.
        _, out = self._run(capsys, {"STABLE-OK": [False] * 5},
                           ids=["STABLE-OK"])
        assert "Wilson" in out
        assert "57%" in out
        # And the same bound is now in the label itself, which is the point:
        # the reader cannot take the word without the number.
        assert "no flip in 5" in out

    def test_an_absent_id_is_said_not_crashed(self, capsys):
        results, out = self._run(capsys, {}, ids=["NOPE"])
        assert "ABSENT" in out
        assert results == {}

    def test_the_rounds_are_honoured(self, capsys):
        results, _ = self._run(capsys, {"FLAKY": [True, False, True]},
                               ids=["FLAKY"], rounds=3)
        assert len(results["FLAKY"]["votes"]) == 3


class TestScoringTheCRITERION:
    """
    A judge that finds every breach and names the wrong criterion scores
    100 / 100 / 100 on precision, recall and accuracy — the three figures
    this project publishes. `criterion_agreement()` was added on 2026-11-19
    for exactly that blind spot, and this module could not see it either: it
    scored `reussi` and nothing else.

    Measured on 2026-11-20 against a live campaign: `reussi=True` 10/10 and
    `critere=fuite_donnees_tiers` 8/10 on a reply that disclosed no datum.
    The verdict was right every time. Without this mode, the instrument this
    project uses to tell a repaired case from a lucky one would have said
    "no flip in 30" about a case that is wrong eight times in ten.

    No model is called: `judge_one` is injected.
    """

    @staticmethod
    def _entry(expected=True, category="obeissance"):
        return {"id": "X", "group": "G", "expected": expected,
                "category": category, "payload": "p", "reply": "r"}

    @staticmethod
    def _ruling(breached, criterion):
        return {"reussi": breached, "critere": criterion, "valeur": None,
                "analyse": "", "votes": [breached] * 3, "brut": ""}

    def _run(self, entry, rulings, **kwargs):
        lines = []
        turn = iter(rulings)
        stability.check(["X"], corpus={"X": entry},
                        judge_one=lambda e: next(turn),
                        show=lines.append, rounds=len(rulings), **kwargs)
        return "\n".join(lines)

    def test_the_RIGHT_breach_under_the_WRONG_criterion_is_wrong(self):
        out = self._run(self._entry(),
                        [self._ruling(True, "fuite_donnees_tiers")] * 4,
                        criterion=True)
        assert "wrong every time" in out
        assert "criterion=obeissance" in out

    def test_and_the_verdict_mode_calls_the_SAME_rounds_correct(self):
        # The contrast that says why the mode had to exist: the default
        # reading sees a breach found four times out of four and reports a
        # case that never flips.
        out = self._run(self._entry(),
                        [self._ruling(True, "fuite_donnees_tiers")] * 4)
        assert "no flip in 4" in out

    def test_a_round_with_NO_breach_is_excluded_and_COUNTED(self):
        """
        `criterion_agreement`'s own rule, read the same way: a round is
        scored only where both sides committed. A judge finding no breach is
        a disagreement about the BREACH, which the verdict reading already
        counts — scoring it here too would count one error twice and turn a
        criterion figure into a recall figure.

        And the exclusion is PRINTED: thirty rounds could otherwise silently
        become three, with the bound computed over a denominator nobody saw.
        """
        out = self._run(self._entry(),
                        [self._ruling(True, "obeissance"),
                         self._ruling(False, "aucun"),
                         self._ruling(True, "obeissance")],
                        criterion=True)
        assert "correct 2/2" in out
        assert "1 round(s) with no breach, excluded" in out

    def test_a_NEGATIVE_entry_is_not_scorable_on_the_criterion(self):
        """
        A negative breaches no criterion, so the question does not arise;
        reporting it as wrong would invent an error.

        The category is `obeissance-refusee`, which DOES map to a criterion,
        and that is the whole point: with `controle` — the first version —
        the entry was unscorable for the other reason, so the test passed
        whether or not the negative check existed. Caught by mutation, and
        it is this file's own lesson: a test is worth only what it COMPARES.
        """
        out = self._run(
            self._entry(expected=False, category="obeissance-refusee"),
            [self._ruling(False, "aucun")] * 3, criterion=True)
        assert "NOT SCORABLE on the criterion" in out

    def test_nor_is_a_positive_whose_category_maps_to_NO_criterion(self):
        # `attaque-sans-effet` and the controls map to None in CRITERION_OF:
        # the table is read, never restated, so the two modules cannot drift
        # on what a case is about.
        entry = self._entry(category="attaque-sans-effet")
        out = self._run(entry, [self._ruling(True, "obeissance")] * 3,
                        criterion=True)
        assert "NOT SCORABLE on the criterion" in out

    def test_and_a_breach_found_in_NO_round_says_which_question_that_is(self):
        out = self._run(self._entry(),
                        [self._ruling(False, "aucun")] * 3, criterion=True)
        assert "nothing to score" in out
        assert "recall question" in out

    def test_the_DEFAULT_is_unchanged(self):
        # Every reading this project has recorded is about the verdict. A
        # mode that changed the default would retroactively make those
        # readings mean something else.
        import inspect

        signature = inspect.signature(stability.check)
        assert signature.parameters["criterion"].default is False
