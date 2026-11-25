"""
Tests for the ATTRIBUTION protocol (2026-11-25): `docs:0` against `docs`,
BOTH arms indirect.

No LLM call and no campaign: `one_campaign` is replaced by a function of known
behaviour, so what is checked is the PROTOCOL — that the arms are two LEVELS
rather than two deliveries, that the level reaches the campaign, that the
channel is required on both sides, and which runs are confirmatory.

Two classes earn their place over and above the protocol itself.

`TestLevel0IsDeliberatelyNOTADeliveryLevel` pins a NON-declaration: the
delivery comparison at level 0 is a different question, so level 0 is absent
from `DELIVERY_LEVELS` on purpose and a delivery run against it still
announces itself exploratory. Without this test, a later reader adds it to that
tuple in one line and believes the result confirmatory.

`TestTheBASELINEIsNotTheControl` pins the reason the arms are paired at all.
The per-register delivery run's file is still on disk, with identical code and
judge, so comparing level 0 against it would be cheaper by half — and it is
refused because its figures were READ while this protocol was written. A test
whose null is a number someone inspected first is not a declared test.
"""

import contextlib
import json
import re

import pytest

import evaluation.measure_modes as modes


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


def _arm(findings=0, criteria=(), requests=0):
    return {"findings": findings, "requests": requests,
            "criteria": list(criteria),
            "severities": ["medium"] * len(criteria),
            "families": [], "aimed_from_objective": 0}


def _plantable():
    def ask(message, history=None):
        return "bonjour"
    ask.conversation = True
    ask.indirect = True
    ask.plant = lambda note: note
    return ask


def _drive(monkeypatch, pairs_data, *, per_register=False, show=None,
           built=None):
    """Run `measure` on the attribution arms with scripted outcomes."""
    calls = []
    sequence = list(pairs_data)

    def one(ask, **kwargs):
        calls.append(kwargs)
        return sequence.pop(0)

    def choose(name, *a, **k):
        if built is not None:
            built.append(name)
        return _plantable()

    monkeypatch.setattr(modes, "one_campaign", one)
    monkeypatch.setattr("targets.choose_target", choose)
    if per_register:
        monkeypatch.setattr(modes, "registers_of", lambda *a, **k: ["x", "y"])
        monkeypatch.setattr(modes, "only_register",
                            lambda *a, **k: contextlib.nullcontext())
    lines = []
    modes.measure(pairs=len(pairs_data) // (4 if per_register else 2),
                  multi_attempts=modes.DELIVERY_ATTEMPTS,
                  turns=modes.TURNS, show=(show or lines.append),
                  arms="attribution", only=(modes.REGISTER_TECHNIQUE,),
                  per_register=per_register)
    return calls, lines


def _attributes(name):
    """
    Does the level this target name denotes ATTRIBUTE the planted note?

    Read from the module that DECLARES the levels, never from
    `ATTRIBUTION_LEVELS`. A first version of the two guards below compared the
    observed order against that very constant — so reversing it reversed both
    sides and the mutation was MUTE. A guard is worth only what it COMPARES,
    for the seventh time in this project.
    """
    from targets.docs import DEFAULT_LEVEL
    from targets.docs import LEVELS as DOCS_LEVELS

    _, _, level = name.partition(":")
    return DOCS_LEVELS[int(level) if level else DEFAULT_LEVEL]["attribute"]


def _cli(monkeypatch, arguments, pairs_data):
    """Drive `main()` itself, never a reading of its source."""
    calls = []
    built = []
    sequence = list(pairs_data)

    def one(ask, **kwargs):
        calls.append(kwargs)
        return sequence.pop(0)

    def choose(name, *a, **k):
        built.append(name)
        return _plantable()

    monkeypatch.setattr(modes, "one_campaign", one)
    monkeypatch.setattr("targets.choose_target", choose)
    monkeypatch.setattr(modes, "registers_of", lambda *a, **k: ["x"])
    monkeypatch.setattr(modes, "only_register",
                        lambda *a, **k: contextlib.nullcontext())
    return modes.main(arguments), calls, built


class TestTheARMSAreTwoLEVELSNotTwoDeliveries:
    """
    THE design decision, and the one the hypothesis rests on: the delivery is
    held FIXED and the attribution is the variable. A fourth delivery run
    would have measured indirect against direct at a new level, which is a
    different question and answers nothing about the heading.

    Every case is parametrised over the FLAT and the PER-REGISTER loop,
    because they are two loops and the arms used to be spelled out in each.
    """

    @pytest.mark.parametrize("per_register", [False, True])
    def test_both_arms_are_INDIRECT(self, monkeypatch, per_register):
        calls, _ = _drive(monkeypatch, [_arm()] * 4,
                          per_register=per_register)
        assert len(calls) == 4
        assert all(call["indirect"] is True for call in calls), (
            "one arm stopped planting, so the comparison became a delivery "
            "run and the attribution stopped being the variable")

    @pytest.mark.parametrize("per_register", [False, True])
    def test_two_targets_are_BUILT_one_per_arm(self, monkeypatch,
                                               per_register):
        built = []
        _drive(monkeypatch, [_arm()] * 4, per_register=per_register,
               built=built)
        assert len(built) == 2 and len(set(built)) == 2, built
        # The PROPERTY, not the constant: one arm attributes the note and the
        # other does not. That is what makes the attribution the variable.
        assert sorted(_attributes(name) for name in built) == [False, True]

    @pytest.mark.parametrize("per_register", [False, True])
    def test_the_bottom_rung_runs_FIRST(self, monkeypatch, per_register):
        # Back to back, the declared arm first, for the reason the other two
        # protocols give: a probabilistic target drifts, and running one arm
        # to completion would let drift masquerade as an effect.
        calls, _ = _drive(monkeypatch, [_arm()] * 4,
                          per_register=per_register)
        assert _attributes(calls[0]["target_name"]) is False, (
            "the arm that ATTRIBUTES the note ran first, so the bottom rung "
            "is no longer the declared arm")
        assert _attributes(calls[1]["target_name"]) is True

    def test_the_level_REACHES_the_campaign(self, monkeypatch):
        """
        The junction, DRIVEN rather than read off the source.

        A level that reaches argparse and not `run_campaign` raises nothing:
        the output would announce `docs:0+docs` and measure one level twice,
        internally consistent and wrong. The 2026-11-23 defect in this very
        module, one axis over.
        """
        code, calls, built = _cli(
            monkeypatch, ["--arms", "attribution", "--pairs", "1"],
            [_arm()] * 2)
        assert code == 0
        assert len(set(built)) == 2, built
        assert sorted(_attributes(name) for name in built) == [False, True]
        assert {c["target_name"] for c in calls} == set(built), (
            "a level that reaches argparse and not the campaign measures one "
            "level twice while the output announces two")

    def test_the_label_is_not_a_target_so_naming_one_is_REFUSED(
            self, monkeypatch, capsys):
        # REFUSED rather than ignored, and rather than announced as a
        # departure that does not happen: accepting it would print
        # "exploratory because you named docs:2" over a run of docs:0
        # against docs.
        with pytest.raises(SystemExit) as refusal:
            _cli(monkeypatch,
                 ["--arms", "attribution", "--target", "docs:2"], [])
        assert refusal.value.code == 2
        assert "nothing to pick" in capsys.readouterr().err

    def test_the_heading_names_BOTH_levels(self, monkeypatch):
        # One level in the heading would be a lie about the other, and the
        # file carries the same label so a resume cannot cross.
        _, lines = _drive(monkeypatch, [_arm()] * 2)
        assert modes.ATTRIBUTION_LABEL in "\n".join(lines)


class TestTheChannelIsRequiredOnBOTHArms:
    """
    The 2026-11-17 lesson one axis over: a wrapper that lost the channel made
    the orchestrator believe it was holding a dialogue the target never saw.
    Here a channel missing from the SECOND arm would be measured as though
    its note had gone in.
    """

    def test_an_arm_with_no_channel_is_REFUSED(self, monkeypatch):
        def choose(name, *a, **k):
            if name == modes.ATTRIBUTION_LEVELS[1]:
                from targets.mock import ask_mock
                return ask_mock
            return _plantable()

        monkeypatch.setattr("targets.choose_target", choose)
        monkeypatch.setattr(modes, "one_campaign",
                            lambda *a, **k: _arm())
        with pytest.raises(RuntimeError):
            modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                          show=lambda *_: None, arms="attribution",
                          only=(modes.REGISTER_TECHNIQUE,))

    def test_and_the_FIRST_arm_is_checked_too(self, monkeypatch):
        def choose(name, *a, **k):
            if name == modes.ATTRIBUTION_LEVELS[0]:
                from targets.mock import ask_mock
                return ask_mock
            return _plantable()

        monkeypatch.setattr("targets.choose_target", choose)
        monkeypatch.setattr(modes, "one_campaign",
                            lambda *a, **k: _arm())
        with pytest.raises(RuntimeError):
            modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                          show=lambda *_: None, arms="attribution",
                          only=(modes.REGISTER_TECHNIQUE,))

    def test_both_WITH_it_measure_normally(self, monkeypatch):
        calls, _ = _drive(monkeypatch, [_arm()] * 2)
        assert len(calls) == 2


class TestWhichRunsAreCONFIRMATORY:

    def _departures(self, **changed):
        spec = dict(target=modes.ATTRIBUTION_LABEL,
                    pairs=modes.ATTRIBUTION_PAIRS,
                    attempts=modes.DELIVERY_ATTEMPTS, turns=modes.TURNS,
                    arms="attribution", only=(modes.REGISTER_TECHNIQUE,),
                    per_register=True)
        spec.update(changed)
        return modes.departures_from_the_protocol(
            spec["target"], spec["pairs"], spec["attempts"], spec["turns"],
            spec["arms"], spec["only"], spec["per_register"])

    def test_the_declared_run_is_clean(self):
        assert self._departures() == []

    def test_a_FLAT_run_is_a_DEPARTURE(self):
        # The comparability with the recorded per-register run rests on the
        # sampling as much as on the scope, so a flat run is not this
        # protocol.
        assert any("PER-REGISTER" in text
                   for text in self._departures(per_register=False))

    def test_the_whole_library_is_a_departure(self):
        assert self._departures(only=()) != []

    def test_another_scope_is_one_too(self):
        assert self._departures(only=("LLM07",)) != []

    def test_a_changed_pair_count_is_one(self):
        assert self._departures(pairs=3) != []

    def test_the_TURN_count_is_NOT_one_here(self):
        # Both arms send one message, so `--turns` means nothing to this
        # protocol and its default must not read as a departure.
        assert self._departures(turns=99) == []

    def test_and_the_OTHER_protocols_are_still_clean(self):
        # `departures_from_the_protocol` was refactored to read the declared
        # values from the spec rather than branch on the arms name. Both
        # older protocols must be unaffected by that.
        assert modes.departures_from_the_protocol(
            "demo", modes.PAIRS, modes.MULTI_ATTEMPTS, modes.TURNS,
            "turns") == []
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery") == []
        assert modes.departures_from_the_protocol(
            "docs", modes.PER_REGISTER_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ("injection-indirecte",), True) == []

    def test_the_CLI_turns_PER_REGISTER_on_and_SAYS_so(self, monkeypatch,
                                                       capsys):
        # Turned on rather than refused, because there is no
        # `--no-per-register` for this to override — and said out loud, since
        # a mode switched in silence is a measurement rewriting itself.
        code, calls, _ = _cli(
            monkeypatch, ["--arms", "attribution", "--pairs", "1"],
            [_arm()] * 2)
        assert code == 0
        assert "PER-REGISTER by declaration" in capsys.readouterr().out

    def test_the_CLI_fills_in_the_declared_SCOPE(self, monkeypatch):
        # So `--arms attribution` alone is confirmatory rather than that
        # protocol pointed at the whole library.
        _, calls, _ = _cli(
            monkeypatch, ["--arms", "attribution", "--pairs", "1"],
            [_arm()] * 2)
        assert all(call["only"] == (modes.REGISTER_TECHNIQUE,)
                   for call in calls)


class TestTheBASELINEIsNotTheControl:
    """
    The cheaper design — run level 0 alone and compare against the
    per-register run's file — is refused because its figures were READ while
    this protocol was written.

    NOT refused for a code confound: the baseline carries fingerprint
    14e9a4d48d2a1b74 and so does HEAD, the vocabulary widening having landed
    before that run. Claiming a confound that does not exist to justify a
    design would be the same sin as denying one that does.
    """

    def test_the_pair_count_is_DERIVED_from_the_baseline_s(self):
        # Declaring a second 6 would let the two drift apart in silence, and
        # the consistency check reported beside the test depends on the two
        # runs pooling the same 36 pairs.
        assert modes.ATTRIBUTION_PAIRS == modes.PER_REGISTER_PAIRS
        assert len(modes.registers_of()) * modes.ATTRIBUTION_PAIRS == 36

    def test_the_scope_is_the_baseline_s(self):
        assert modes.ARMS["attribution"]["scopes"] == (
            (modes.REGISTER_TECHNIQUE,),)
        assert (modes.REGISTER_TECHNIQUE,) in modes.DELIVERY_SCOPES, (
            "the baseline's scope must stay declared for the delivery arms "
            "too, or the two runs are not the same measurement of payloads")

    def test_the_announcement_says_WHY_the_pairing_is_needed(self,
                                                             monkeypatch):
        _, lines = _drive(monkeypatch, [_arm()] * 2)
        joined = "\n".join(lines)
        assert "ATTRIBUTION is the variable" in joined
        assert "drift" in joined
        assert "read while this" in joined, (
            "the announcement must say the baseline's figures were already "
            "read, which is the reason the arms are paired at all")


class TestLevel0IsDeliberatelyNOTADeliveryLevel:
    """
    A NON-declaration, pinned so it cannot be undone in one line.

    Indirect against direct AT level 0 is a different question from "does the
    attribution suppress the indirect arm", and nobody has declared a
    protocol for it. Adding `docs:0` to `DELIVERY_LEVELS` would make such a
    run print "Confirmatory under the GENERALITY protocol" over a
    measurement no protocol describes.
    """

    def test_it_is_absent_from_the_delivery_levels(self):
        assert "docs:0" not in modes.DELIVERY_LEVELS
        assert modes.DELIVERY_LEVELS == ("docs:2", "docs:3")

    def test_so_a_delivery_run_against_it_is_EXPLORATORY(self):
        departures = modes.departures_from_the_protocol(
            "docs:0", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery")
        assert any("docs:0" in text for text in departures)

    def test_but_it_IS_a_bundled_target_so_nothing_blocks_the_run(self):
        # Exploratory, not forbidden: the machine flags, the human decides.
        from targets import is_bundled_target
        assert is_bundled_target("docs:0")


class TestTheOutcomeIsKeptForCOMPARABILITYNotFairness:
    """
    The delivery protocol restricted the outcome to correct a FAIRNESS
    problem: `obeissance` is unscorable for an indirect attempt, so counting
    it handed the direct arm a whole register. Here both arms are indirect,
    the bar applies equally and corrects nothing — the restriction is kept so
    these figures sit on the same footing as the three recorded runs.
    """

    def test_it_is_the_SAME_outcome_as_the_delivery_protocol(self):
        assert (modes.ARMS["attribution"]["outcome"]
                is modes.ARMS["delivery"]["outcome"])

    def test_the_obeissance_line_is_a_CHECK_on_BOTH_arms(self, monkeypatch):
        # The structural bar predicts zero on each side; a non-zero would
        # mean that claim is wrong, so the count is reported for both.
        lines = []
        modes._summary([{"unattributed": _arm(1, ["divulgation"]),
                         "attributed": _arm(1, ["obeissance"])}],
                       show=lines.append, target=modes.ATTRIBUTION_LABEL,
                       arms="attribution")
        joined = "\n".join(lines)
        assert joined.count("`obeissance` finding(s)") == 2
        assert "the bar predicts 0" in joined

    def test_and_the_DELIVERY_wording_is_not_used_here(self, monkeypatch):
        # "for the direct arm" names an arm this comparison does not have.
        lines = []
        modes._summary([{"unattributed": _arm(), "attributed": _arm()}],
                       show=lines.append, target=modes.ATTRIBUTION_LABEL,
                       arms="attribution")
        assert "for the direct arm" not in "\n".join(lines)

    def test_the_DELIVERY_summary_keeps_its_own_wording(self):
        # The contrast, without which the test above would pass on a module
        # that had simply dropped the delivery line.
        lines = []
        modes._summary([{"indirect": _arm(), "direct": _arm(1,
                                                            ["obeissance"])}],
                       show=lines.append, target="docs", arms="delivery")
        assert "for the direct arm" in "\n".join(lines)


class TestTheTestAndItsHONESTY:

    def test_the_declared_hypothesis_is_REMOVING_the_attribution(self):
        assert (modes.ARMS["attribution"]["hypothesis"]
                == "removing the attribution finds more")

    def test_a_REVERSED_result_is_flagged_and_NOT_the_declared_test(
            self, monkeypatch):
        lines = []
        _drive(monkeypatch,
               [_arm(), _arm(2, ["divulgation", "abus_outils"])] * 3,
               show=lines.append)
        joined = "\n".join(lines)
        assert "runs the OTHER way" in joined
        assert "NOT the declared test" in joined
        assert "the attributed level finds more" in joined

    def test_a_FAVOURABLE_result_is_not_flagged(self, monkeypatch):
        lines = []
        _drive(monkeypatch,
               [_arm(2, ["divulgation", "abus_outils"]), _arm()] * 3,
               show=lines.append)
        assert "runs the OTHER way" not in "\n".join(lines)


class TestTheFileRecordsWHICHComparison:

    def _write(self, path, **protocol):
        block = {"pairs": modes.ATTRIBUTION_PAIRS, "multi_attempts": 6,
                 "turns": modes.TURNS, "threshold": 0.05,
                 "judge": "fake/judge", "declared": True,
                 "arms": "attribution", "only": [modes.REGISTER_TECHNIQUE],
                 "per_register": True, "code": "aaaa"}
        block.update(protocol)
        path.write_text(json.dumps(
            {"complete": False, "target": modes.ATTRIBUTION_LABEL,
             "protocol": block,
             "pairs": [{"unattributed": _arm(), "attributed": _arm(),
                        "register": 0}]}), encoding="utf-8")

    def test_the_arms_and_the_LABEL_are_in_the_block(self, monkeypatch,
                                                     tmp_path):
        output = tmp_path / "a.json"
        calls = []
        sequence = [_arm()] * 4

        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k)
                            or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=2, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      output=str(output), show=lambda *_: None,
                      arms="attribution", only=(modes.REGISTER_TECHNIQUE,))
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["protocol"]["arms"] == "attribution"
        assert written["target"] == modes.ATTRIBUTION_LABEL, (
            "a file naming one level could resume into the wrong measurement")

    def test_a_DELIVERY_file_is_REFUSED(self, tmp_path):
        output = tmp_path / "a.json"
        self._write(output, arms="delivery")
        with pytest.raises(SystemExit, match="comparison"):
            modes.already_measured(
                str(output), modes.ATTRIBUTION_LABEL,
                {"pairs": modes.ATTRIBUTION_PAIRS, "multi_attempts": 6,
                 "turns": modes.TURNS, "arms": "attribution",
                 "only": [modes.REGISTER_TECHNIQUE], "per_register": True,
                 "code": "aaaa", "judge": "fake/judge"},
                show=lambda *_: None)

    def test_and_the_MIRROR_holds_on_the_LABEL(self, tmp_path):
        # TWO independent refusals, and this one shows the second: a delivery
        # run resuming an attribution file is stopped by the TARGET before
        # the arms are even compared, because the label is not a level. The
        # test above is the arms check itself, where the target matches.
        output = tmp_path / "a.json"
        self._write(output)
        # Escaped: the label carries a `+`, which is a regex
        # metacharacter -- so an unescaped match would fail on a message
        # that names it perfectly.
        with pytest.raises(SystemExit,
                           match=re.escape(modes.ATTRIBUTION_LABEL)):
            modes.already_measured(
                str(output), "docs",
                {"pairs": modes.DELIVERY_PAIRS, "multi_attempts": 6,
                 "turns": modes.TURNS, "arms": "delivery", "only": [],
                 "per_register": False, "code": "aaaa",
                 "judge": "fake/judge"},
                show=lambda *_: None)

    def test_the_SAME_comparison_resumes(self, tmp_path):
        output = tmp_path / "a.json"
        self._write(output)
        done = modes.already_measured(
            str(output), modes.ATTRIBUTION_LABEL,
            {"pairs": modes.ATTRIBUTION_PAIRS, "multi_attempts": 6,
             "turns": modes.TURNS, "arms": "attribution",
             "only": [modes.REGISTER_TECHNIQUE], "per_register": True,
             "code": "aaaa", "judge": "fake/judge"},
            show=lambda *_: None)
        assert len(done) == 1


class TestTheOlderPROTOCOLSAreUntouched:
    """
    Their figures are published — 17-1 at level 1, the three-level table,
    20-5 and 19-0 and 1-31 for the delivery runs. A third comparison that
    moved their constants or reworded their summaries would make those
    figures describe an instrument that no longer exists.
    """

    def test_the_turns_constants_have_not_moved(self):
        assert modes.TARGET == "demo"
        assert modes.MULTI_ATTEMPTS == 3
        assert modes.TURNS == 3
        assert modes.PAIRS == 20
        assert modes.GENERALITY_LEVELS == ("demo:2", "demo:3")

    def test_the_delivery_constants_have_not_moved(self):
        assert modes.DELIVERY_TARGET == "docs"
        assert modes.DELIVERY_PAIRS == 20
        assert modes.DELIVERY_ATTEMPTS == 6
        assert modes.PER_REGISTER_PAIRS == 6
        assert set(modes.JOINTLY_SCORABLE) == {
            "divulgation", "abus_outils", "fuite_donnees_tiers"}

    def test_the_turns_summary_wording_is_unchanged(self):
        lines = []
        modes._summary([{"multi": _arm(2), "single": _arm(1)}],
                       show=lines.append, arms="turns")
        joined = "\n".join(lines)
        assert "multi-turn  finds more: 1" in joined
        assert "DECLARED test (multi-turn finds more)" in joined

    def test_the_turns_arm_still_gets_attempts_times_turns(self,
                                                           monkeypatch):
        # The one place the arms genuinely differ in their BUDGET, kept out
        # of the shared `two_campaigns` for that reason.
        calls = []
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k)
                            or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=1, multi_attempts=3, turns=3,
                      show=lambda *_: None, target="demo", arms="turns")
        assert calls[0]["attempts"] == 3
        assert calls[1]["attempts"] == 9

    def test_the_delivery_arms_still_differ_in_their_DELIVERY(self,
                                                             monkeypatch):
        calls = []
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k)
                            or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lambda *_: None, target="docs", arms="delivery")
        assert calls[0]["indirect"] is True
        assert calls[1]["indirect"] is False
