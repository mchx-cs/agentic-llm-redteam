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


class TestTheBreakdownIsREADThroughTheReport:
    """
    The by-criterion and by-severity lines printed NOTHING on the first real
    run (2026-11-19). `one_campaign` read the REPORT's field names off the
    CAMPAIGN's raw result, where a finding carries `payload` and `verdict` as
    sub-objects and severity does not exist at all -- it is DERIVED by the
    rules in `report.py`.

    Three of the four fields came back `None`, the counts beside them were
    right, and so nothing looked broken. Every test above feeds `_summary`
    ready-made dicts, so not one of them covered where those dicts come from:
    the junction defect this project has met repeatedly, two pieces correct on
    their own and nothing on the glue.
    """

    @staticmethod
    def _raw(criterion="divulgation", replay="confirmed", from_objective=None):
        """A campaign result in the shape `run_campaign` really returns."""
        attempt = {"technique": "t", "owasp_family": "LLM02",
                   "objective": "secret", "transformation": "identity",
                   "text": "payload"}
        if from_objective:
            attempt = dict(attempt, pyrit_objective_from=from_objective)
        return {
            "status": "findings",
            "profile": None,
            "plan": {"attempts": [attempt], "candidates": [attempt],
                     "skipped": []},
            "launched": [attempt],
            "observations": [],
            "call_log": {"calls": 1, "tokens": 10, "truncated_replies": []},
            "findings": [{
                "attempt": 1,
                "payload": attempt,
                "reply": "réponse",
                "verdict": {"reussi": True, "critere": criterion,
                            "valeur": "V", "analyse": "a",
                            "votes": [True, True, True]},
                "replay_check": ({"status": replay, "explanation": ""}
                                 if replay else None),
                "truncated": False,
            }],
        }

    def _run(self, monkeypatch, raw):
        import main
        monkeypatch.setattr(main, "run_campaign", lambda **kwargs: raw)
        return modes.one_campaign(lambda m, h=None: "r", multiturn=None,
                                  attempts=1, turns=None, show=lambda *_: None)

    def test_the_criterion_comes_back_NAMED(self, monkeypatch):
        got = self._run(monkeypatch, self._raw(criterion="abus_outils"))
        assert got["criteria"] == ["abus_outils"], (
            "the criterion lives in finding['verdict']['critere'], not at the "
            "finding's top level: reading it there gives None, which is what "
            "silenced the breakdown")

    def test_the_SEVERITY_is_graded_and_not_merely_copied(self, monkeypatch):
        """
        The row that decides the comparison. A multi-turn campaign can never
        reach `high`, since `high` needs ("divulgation", "confirmed") and
        replay re-sends ONE payload, which a conversation has none of. So a
        tie in COUNT is not a tie in WORTH -- and severity is not a field of
        the campaign's result, it is a RULE applied to the verdict and the
        replay.
        """
        got = self._run(monkeypatch, self._raw("divulgation", "confirmed"))
        assert got["severities"] == ["high"]

        got = self._run(monkeypatch, self._raw("obeissance", None))
        assert got["severities"] == ["medium"], (
            "graded by report.SEVERITIES -- a second copy of that rule here "
            "would drift from the one the operator's report shows")

    def test_the_family_comes_back_NAMED(self, monkeypatch):
        got = self._run(monkeypatch, self._raw())
        assert got["families"] == ["LLM02"]

    def test_the_coverage_caveat_is_COUNTED_not_assumed_zero(self, monkeypatch):
        """
        `aimed_from_objective` is computed by `build_report` and lives in its
        coverage: the campaign's raw result has no `coverage` key at all, so
        reading it there returns the default 0 and the caveat NEVER prints.
        On the real run all 60 multi-turn attempts pursued a reconnaissance
        objective, and the warning was suppressed for every one of them.
        """
        got = self._run(monkeypatch,
                        self._raw(from_objective="objective"))
        assert got["aimed_from_objective"] == 1

        got = self._run(monkeypatch,
                        self._raw(from_objective="payload-text"))
        assert got["aimed_from_objective"] == 0, (
            "an attempt pursuing the payload's own text DOES exercise the "
            "family it names: counting it here would warn about nothing")


class TestTheGENERALITYProtocol:
    """
    The reservation this project recorded against its own result: the mode
    comparison settled the question for ONE target at ONE defence level, and
    `TARGET` was a module constant that `one_campaign` read as a GLOBAL.

    So the instrument could not ask the question its own docstring named as
    open, and the protocol declaring `demo:2` and `demo:3` would have been
    prose. The tests below are what makes it executable.
    """

    @staticmethod
    def _raw():
        return TestTheBreakdownIsREADThroughTheReport._raw()

    def test_the_target_REACHES_the_campaign(self, monkeypatch):
        """
        The junction, DRIVEN and not read.

        On 2026-11-19 an argument was spliced into `tuple(arguments.only)`
        instead of the call it was meant for, and thirteen tests passed over
        it because not one of them drove `main()`. A `--target` that reaches
        argparse and not `run_campaign` would measure level 1 under a level-3
        heading — the worst shape available here, since the output would be
        internally consistent and wrong.
        """
        seen = []
        import main as orchestrator
        monkeypatch.setattr(
            orchestrator, "run_campaign",
            lambda **kwargs: seen.append(kwargs) or self._raw())
        modes.main(["--target", "demo:3", "--pairs", "1"])

        assert seen, "no campaign ran at all"
        assert {kwargs["target_name"] for kwargs in seen} == {"demo:3"}, (
            "the measured target must reach run_campaign; reading the module "
            "constant there makes every level measure level 1")

    def test_ONE_run_measures_ONE_level(self, monkeypatch):
        """
        Levels are NEVER pooled. Putting targets of different resistances in
        one test makes no sense, and this project recorded that twice before
        declaring it here — the multi-turn harvest's leaks came almost
        entirely from level 1.

        A run that alternated levels would still produce a sign test, and
        nothing in the output would say what it was over.
        """
        seen = []
        import main as orchestrator
        monkeypatch.setattr(
            orchestrator, "run_campaign",
            lambda **kwargs: seen.append(kwargs) or self._raw())
        modes.measure(pairs=3, multi_attempts=1, turns=1, target="demo:2",
                      show=lambda *_: None)

        assert len(seen) == 6, "three pairs, two modes each"
        assert {kwargs["target_name"] for kwargs in seen} == {"demo:2"}

    def test_the_target_reaches_the_REPORT_too(self, monkeypatch):
        # The breakdown is read through `build_report`, which is the one place
        # in this project that grades. Handing it the constant while the
        # campaign ran elsewhere would be the two halves disagreeing about
        # which target was measured.
        seen = []
        import main as orchestrator
        import report
        monkeypatch.setattr(orchestrator, "run_campaign",
                            lambda **kwargs: self._raw())
        built = report.build_report
        monkeypatch.setattr(report, "build_report",
                            lambda result, **kwargs: seen.append(kwargs)
                            or built(result, **kwargs))
        modes.one_campaign(lambda m, h=None: "r", multiturn=None, attempts=1,
                           turns=None, show=lambda *_: None,
                           target_name="demo:2")
        assert [kwargs["target"] for kwargs in seen] == ["demo:2"]

    def test_a_DECLARED_level_is_not_flagged_exploratory(self, monkeypatch,
                                                         capsys):
        """
        `demo:2` and `demo:3` are declared in a protocol committed before
        either was run, so they are confirmatory. Flagging them would teach
        the reader to ignore the flag — and this project has removed a guard
        for crying wrong twice in four.
        """
        monkeypatch.setattr(modes, "measure", lambda *a, **k: [])
        for level in modes.GENERALITY_LEVELS:
            modes.main(["--target", level])
            out = capsys.readouterr().out
            assert "Protocol CHANGED" not in out, (
                f"{level} is declared by the generality protocol")
            assert "Confirmatory under the GENERALITY protocol" in out
            assert level in out

    def test_but_an_UNDECLARED_target_says_so(self, monkeypatch, capsys):
        # The other half, and without it the test above would pass on a module
        # that flags nothing at all. Deciding after the fact which targets
        # "count" is the post hoc selection the string protocol refused on
        # 2026-11-17.
        monkeypatch.setattr(modes, "measure", lambda *a, **k: [])
        modes.main(["--target", "records"])
        out = capsys.readouterr().out
        assert "Protocol CHANGED" in out and "exploratory" in out
        assert "records" in out

    def test_the_output_file_records_its_own_QUESTION(self, monkeypatch,
                                                      tmp_path):
        """
        A run killed at pair 28 on 2026-11-17 could not be shown to be the
        same measurement as the next one, because its log never said what it
        had asked. With three levels producing three files, two of them would
        otherwise be distinguishable only by their filename.
        """
        import json

        import main as orchestrator
        monkeypatch.setattr(orchestrator, "run_campaign",
                            lambda **kwargs: self._raw())
        path = tmp_path / "modes.json"
        modes.measure(pairs=1, multi_attempts=1, turns=1, output=str(path),
                      target="demo:2", show=lambda *_: None)

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["target"] == "demo:2"
        assert saved["protocol"]["pairs"] == 1
        assert saved["protocol"]["declared"] is False, (
            "one pair is not the declared protocol, and the file has to say "
            "so: a figure nobody can place is not a measurement")

    def test_and_a_declared_run_is_recorded_as_declared(self, monkeypatch,
                                                        tmp_path):
        # The contrast that makes the field mean something. A file where
        # `declared` is always False would carry no information at all.
        import json

        import main as orchestrator
        monkeypatch.setattr(orchestrator, "run_campaign",
                            lambda **kwargs: self._raw())
        path = tmp_path / "modes.json"
        modes.measure(pairs=modes.PAIRS, multi_attempts=modes.MULTI_ATTEMPTS,
                      turns=modes.TURNS, output=str(path), target="demo:3",
                      show=lambda *_: None)
        assert json.loads(path.read_text(encoding="utf-8"))[
            "protocol"]["declared"] is True

    def test_the_summary_NAMES_the_level_it_is_over(self, capsys):
        # Three summaries identical in shape, and a reader comparing two of
        # them must not have to trust the filename. The same reason
        # `evaluate_judge` announces a restriction ABOVE its figures.
        empty = {"findings": 0, "requests": 9, "criteria": [],
                 "severities": [], "families": [], "aimed_from_objective": 0}
        results = [{"multi": dict(empty, findings=1), "single": dict(empty)}]
        modes._summary(results, target="demo:3")
        assert "demo:3" in capsys.readouterr().out
