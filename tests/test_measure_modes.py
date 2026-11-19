"""
Tests for the mode-against-mode protocol (2026-11-19).

No LLM call and no PyRIT: `run_campaign` is replaced by a function of known
behaviour, so what is checked is the PROTOCOL — the normalisation, the
pairing, the direction of the test and the honesty of the reverse report —
rather than anything a model does.

The protocol is the deliverable here. A declared protocol nobody can check is
prose, and this project has already paid for a measurement whose arms differed
in something other than the declared variable.
"""

import pytest

import evaluation.measure_modes as modes


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """`tests/` never calls a model: held by the code, not by faith."""
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestTheNormalisationIsEqualTARGETREQUESTS:
    """
    The decision that shapes the result. Not equal attempts, which would hand
    multi-turn ~4.5 times the resources; not equal tokens, which cost cents
    and are nobody's constraint. The project's own recorded constraints on a
    real target all count requests TO THE TARGET.
    """

    def test_the_single_turn_arm_gets_attempts_times_turns(self, monkeypatch):
        asked = []
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: asked.append(k) or {
                                "findings": 0, "requests": 0, "criteria": [],
                                "severities": [], "families": [],
                                "aimed_from_objective": 0})
        modes.measure(pairs=1, multi_attempts=3, turns=3,
                      show=lambda *_: None)
        multi, single = asked[0], asked[1]
        assert multi["attempts"] == 3 and multi["turns"] == 3
        assert single["attempts"] == 9, (
            "the single-turn arm must get attempts x turns, or the two modes "
            "do not spend the same number of requests on the target")

    def test_the_requests_actually_spent_are_COUNTED(self):
        # Measured, never assumed: the normalisation is the heart of the
        # protocol, so its audit has to be visible.
        calls = []
        wrapped, counter = modes.counting(lambda m, h=None: calls.append(m))
        wrapped("un")
        wrapped("deux")
        assert counter["n"] == 2

    def test_the_counter_preserves_the_conversation_capability(self):
        # Declared, never guessed: a wrapper that dropped the flag would make
        # the multi-turn arm refuse, and the measurement would quietly become
        # single-turn against single-turn.
        def ask(message, history=None):
            return "r"
        ask.conversation = True
        wrapped, _ = modes.counting(ask)
        assert wrapped.conversation is True


class TestThePairingRunsBothModesBackToBack:
    def test_multi_turn_runs_first_then_single(self, monkeypatch):
        order = []
        monkeypatch.setattr(
            modes, "one_campaign",
            lambda ask, **k: order.append(
                "multi" if k["multiturn"] else "single") or {
                    "findings": 0, "requests": 0, "criteria": [],
                    "severities": [], "families": [],
                    "aimed_from_objective": 0})
        modes.measure(pairs=2, show=lambda *_: None)
        assert order == ["multi", "single", "multi", "single"], (
            "a mode run to completion before the other lets the target's "
            "drift masquerade as an effect")


class TestTheTestAndItsHONESTY:
    @staticmethod
    def _summary(pairs):
        said = []
        modes._summary(pairs, said.append)
        return " ".join(said)

    @staticmethod
    def _pair(multi, single):
        empty = {"criteria": [], "severities": [], "families": [],
                 "aimed_from_objective": 0, "requests": 9}
        return {"multi": {**empty, "findings": multi},
                "single": {**empty, "findings": single}}

    def test_a_clear_multiturn_win_is_significant(self):
        text = self._summary([self._pair(2, 0)] * 6)
        assert "DECLARED test" in text and "SIGNIFICANT" in text

    def test_the_REVERSE_direction_is_reported_and_FLAGGED(self):
        """
        The adaptation series declared one direction on 2026-11-12, saw the
        other, and said so: the declared hypothesis gave p = 0.99 and the
        reverse 0.032. Quoting the reverse p as if it had been the hypothesis
        is the p-hacking the protocol exists to prevent, and hiding it is the
        other half of the same dishonesty.
        """
        text = self._summary([self._pair(0, 2)] * 6)
        assert "runs the OTHER way" in text
        assert "NOT the declared test" in text

    def test_no_reverse_report_when_the_declared_direction_leads(self):
        # The contrast: printing it always would make the flag meaningless.
        text = self._summary([self._pair(2, 0)] * 6)
        assert "runs the OTHER way" not in text

    def test_ties_leave_the_sign_test_alone(self):
        # A sign test counts discordant pairs; ties carry no information and
        # must not be split either way.
        text = self._summary([self._pair(1, 1)] * 10)
        assert "tie                   : 10" in text
        assert "p = 1.0000" in text


class TestWhatIsREPORTEDBesideTheTest:
    @staticmethod
    def _summary(pairs):
        said = []
        modes._summary(pairs, said.append)
        return " ".join(said)

    def test_the_severities_are_shown(self):
        """
        A tie in COUNT is not a tie in WORTH: a multi-turn campaign can never
        produce a `high` finding, since `high` needs
        `("divulgation", "confirmed")` and replay re-sends one payload, which
        a conversation has none of.
        """
        text = self._summary([{
            "multi": {"findings": 1, "requests": 9, "criteria": ["obeissance"],
                      "severities": ["medium"], "families": [],
                      "aimed_from_objective": 3},
            "single": {"findings": 1, "requests": 9,
                       "criteria": ["divulgation"], "severities": ["high"],
                       "families": [], "aimed_from_objective": 0},
        }])
        assert "medium 1" in text and "high 1" in text

    def test_the_target_requests_of_each_mode_are_shown(self):
        text = self._summary([{
            "multi": {"findings": 0, "requests": 9, "criteria": [],
                      "severities": [], "families": [],
                      "aimed_from_objective": 0},
            "single": {"findings": 0, "requests": 14, "criteria": [],
                       "severities": [], "families": [],
                       "aimed_from_objective": 0},
        }])
        # 14 against 9: the replay requests the declared bias is about.
        assert "over 9 target request(s)" in text
        assert "over 14 target request(s)" in text

    def test_the_coverage_caveat_is_carried_through(self):
        # The overstatement corrected on 2026-11-19, and this is the first
        # measurement that exercises it.
        text = self._summary([{
            "multi": {"findings": 0, "requests": 9, "criteria": [],
                      "severities": [], "families": [],
                      "aimed_from_objective": 3},
            "single": {"findings": 0, "requests": 9, "criteria": [],
                       "severities": [], "families": [],
                       "aimed_from_objective": 0},
        }])
        assert "aimed at and not what was sent" in text


class TestTheProtocolIsSTATEDBeforeTheFigures:
    def test_the_declared_bias_is_in_the_header(self, monkeypatch, capsys):
        # In the output, not only in the docstring: a reader of the result
        # must meet the bias before the numbers.
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: {
                                "findings": 0, "requests": 0, "criteria": [],
                                "severities": [], "families": [],
                                "aimed_from_objective": 0})
        modes.measure(pairs=1)
        out = capsys.readouterr().out
        assert "Equal TARGET REQUESTS" in out
        assert "favours MULTI-TURN" in out

    def test_a_changed_protocol_announces_itself(self, monkeypatch, capsys):
        monkeypatch.setattr(modes, "measure", lambda *a, **k: [])
        modes.main(["--pairs", "3"])
        out = capsys.readouterr().out
        assert "Protocol CHANGED" in out
        assert "exploratory" in out
