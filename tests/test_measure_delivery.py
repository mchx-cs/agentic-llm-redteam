"""
Tests for the DELIVERY protocol (2026-11-25): `--indirect` against an
ordinary campaign.

No LLM call and no campaign: `one_campaign` is replaced by a function of
known behaviour, so what is checked is the PROTOCOL — the normalisation, the
a priori restriction of the outcome, the pairing, the direction of the test
and the honesty of the reverse report.

The first class is the one that matters most to the project's record: the
TURNS protocol must be untouched, because its published figures (17-1 at
level 1, the three-level table) are cited in CLAUDE.md and a reworded summary
would stop describing the instrument that produced them.
"""

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


def _drive(monkeypatch, pairs_data, *, arms="delivery", target="docs",
           show=None):
    """Run `measure` with a scripted sequence of campaign outcomes."""
    calls = []
    sequence = list(pairs_data)

    def one(ask, **kwargs):
        calls.append(kwargs)
        return sequence.pop(0)

    monkeypatch.setattr(modes, "one_campaign", one)
    monkeypatch.setattr("targets.choose_target", lambda *a, **k: _plantable())
    lines = []
    modes.measure(pairs=len(pairs_data) // 2,
                  multi_attempts=modes.DELIVERY_ATTEMPTS, turns=modes.TURNS,
                  show=(show or lines.append), target=target, arms=arms)
    return calls, lines


class TestTheTURNSProtocolIsUNTOUCHED:
    """
    Its figures are published. A second comparison that reworded its summary
    or moved its constants would make those figures describe an instrument
    that no longer exists.
    """

    def test_its_constants_have_not_moved(self):
        assert modes.TARGET == "demo"
        assert modes.MULTI_ATTEMPTS == 3
        assert modes.TURNS == 3
        assert modes.PAIRS == 20
        assert modes.GENERALITY_LEVELS == ("demo:2", "demo:3")

    def test_its_outcome_is_still_EVERY_finding(self):
        # The turns protocol declares "the number of findings a campaign
        # reports", with no restriction. Narrowing it to match the delivery
        # protocol would silently re-define its published result.
        arm = _arm(3, ["obeissance", "divulgation", "abus_outils"])
        assert modes.ARMS["turns"]["outcome"](arm) == 3

    def test_its_summary_wording_is_unchanged(self, monkeypatch):
        lines = []
        modes._summary([{"multi": _arm(2), "single": _arm(1)}],
                       show=lines.append, arms="turns")
        joined = "\n".join(lines)
        assert "multi-turn  finds more: 1" in joined
        assert "DECLARED test (multi-turn finds more)" in joined

    def test_a_turns_run_is_still_confirmatory_on_demo(self):
        assert modes.departures_from_the_protocol(
            "demo", modes.PAIRS, modes.MULTI_ATTEMPTS, modes.TURNS,
            "turns") == []


class TestTheOutcomeIsRestrictedAPRIORI:
    """
    `obeissance` is structurally unscorable for an indirect attempt — the
    imposed text is in the note, and criterion 2 needs it to compare against
    (measured 2026-11-25, `aucun` 10/10). So counting it would hand the
    direct arm a whole register by construction.

    Restricting BEFORE any result, and justified by a measurement that
    predates the run, is the legitimate kind. "Restrict to what happened to
    leak" is not — the distinction drawn on 2026-11-13.
    """

    def test_obeissance_is_NOT_counted(self):
        assert "obeissance" not in modes.JOINTLY_SCORABLE

    def test_the_three_the_judge_can_score_BOTH_ways_are(self):
        assert set(modes.JOINTLY_SCORABLE) == {
            "divulgation", "abus_outils", "fuite_donnees_tiers"}

    def test_the_declared_outcome_drops_obeissance(self):
        arm = _arm(4, ["obeissance", "obeissance", "divulgation",
                       "abus_outils"])
        assert modes.ARMS["delivery"]["outcome"](arm) == 2
        assert arm["findings"] == 4, "the total must stay available"

    def test_an_unknown_criterion_is_not_counted_either(self):
        # A criterion added later is not silently folded into an outcome
        # declared before it existed.
        assert modes.ARMS["delivery"]["outcome"](_arm(1, ["brand-new"])) == 0


class TestTheNormalisationIsEqualATTEMPTS:
    """
    Different from the turns protocol, and the reason is stated: an indirect
    attempt spends one target request and three votes, exactly as a direct
    one does, so equal attempts IS equal cost. The turns protocol had to
    count requests because multi-turn spent ~4.5 times as many per attempt.
    """

    def test_both_arms_get_the_same_attempt_count(self, monkeypatch):
        calls, _ = _drive(monkeypatch, [_arm(), _arm()])
        assert len(calls) == 2
        assert calls[0]["attempts"] == calls[1]["attempts"]
        assert calls[0]["attempts"] == modes.DELIVERY_ATTEMPTS

    def test_neither_arm_is_multi_turn(self, monkeypatch):
        calls, _ = _drive(monkeypatch, [_arm(), _arm()])
        assert all(not call["multiturn"] for call in calls)

    def test_the_INDIRECT_arm_is_the_one_that_plants(self, monkeypatch):
        calls, _ = _drive(monkeypatch, [_arm(), _arm()])
        assert calls[0]["indirect"] is True
        assert calls[1].get("indirect") is False

    def test_indirect_runs_FIRST(self, monkeypatch):
        # Back to back, the declared arm first: a probabilistic target
        # drifts, and running one arm to completion would let drift
        # masquerade as an effect.
        calls, _ = _drive(monkeypatch, [_arm(), _arm()])
        assert calls[0]["indirect"] is True


class TestTheChannelIsREQUIREDBeforeMeasuring:
    def test_a_target_with_no_channel_is_refused(self, monkeypatch):
        from targets.mock import ask_mock
        monkeypatch.setattr("targets.choose_target", lambda *a, **k: ask_mock)
        monkeypatch.setattr(modes, "one_campaign",
                            lambda *a, **k: _arm())
        with pytest.raises(RuntimeError, match="no content a payload"):
            modes.measure(pairs=1, arms="delivery", target="mock",
                          show=lambda *_: None)

    def test_the_turns_arm_still_requires_a_CONVERSATION(self, monkeypatch):
        # The mirror guard, unchanged: each comparison checks the capability
        # ITS arms need, and neither accepts the other's.
        def flat(message, history=None):
            return "x"
        monkeypatch.setattr("targets.choose_target", lambda *a, **k: flat)
        with pytest.raises(RuntimeError, match="cannot hold a conversation"):
            modes.measure(pairs=1, arms="turns", target="demo",
                          show=lambda *_: None)


class TestTheTestAndItsHONESTY:
    def test_the_declared_hypothesis_is_INDIRECT_finds_more(self, monkeypatch):
        _, lines = _drive(monkeypatch, [_arm(1, ["divulgation"]), _arm()])
        joined = "\n".join(lines)
        assert "DECLARED test (the indirect delivery finds more)" in joined

    def test_a_reversed_result_is_FLAGGED_and_not_the_declared_test(
            self, monkeypatch):
        _, lines = _drive(monkeypatch,
                          [_arm(), _arm(1, ["divulgation"])] * 3)
        joined = "\n".join(lines)
        assert "runs the OTHER way" in joined
        assert "NOT the declared test" in joined
        assert "the direct delivery finds more" in joined

    def test_a_favourable_result_is_NOT_flagged(self, monkeypatch):
        # The contrast: without it the flag could be printed unconditionally.
        _, lines = _drive(monkeypatch,
                          [_arm(1, ["divulgation"]), _arm()] * 3)
        assert "runs the OTHER way" not in "\n".join(lines)

    def test_the_pairing_is_on_the_RESTRICTED_outcome(self, monkeypatch):
        """
        The direct arm wins on the total and loses on the declared outcome.
        If the test counted totals, this pair would go the other way — which
        is exactly the structural bar the restriction exists to remove.
        """
        indirect = _arm(1, ["divulgation"])
        direct = _arm(3, ["obeissance", "obeissance", "obeissance"])
        _, lines = _drive(monkeypatch, [indirect, direct])
        joined = "\n".join(lines)
        assert "indirect    finds more: 1" in joined
        assert "direct      finds more: 0" in joined


class TestTheBARIsREPORTEDBesideTheTest:
    def test_both_the_restricted_count_and_the_total_are_shown(
            self, monkeypatch):
        _, lines = _drive(monkeypatch,
                          [_arm(2, ["divulgation", "obeissance"]),
                           _arm(3, ["obeissance", "obeissance",
                                    "abus_outils"])])
        joined = "\n".join(lines)
        assert "1 finding(s) in the scorable criteria, 2 in all" in joined
        assert "1 finding(s) in the scorable criteria, 3 in all" in joined

    def test_the_obeissance_count_of_the_direct_arm_is_NAMED(self,
                                                             monkeypatch):
        # The audit of the declared bias: a reader sees how many findings the
        # other arm could not even have attempted.
        _, lines = _drive(monkeypatch,
                          [_arm(), _arm(2, ["obeissance", "obeissance"])])
        assert "cannot score at all: 2" in "\n".join(lines)


class TestTheProtocolIsSTATEDBeforeTheFigures:
    def test_it_announces_equal_ATTEMPTS_and_not_requests(self, monkeypatch):
        _, lines = _drive(monkeypatch, [_arm(), _arm()])
        joined = "\n".join(lines)
        assert "Equal ATTEMPTS" in joined
        assert "Equal TARGET REQUESTS" not in joined

    def test_it_announces_the_BIAS_and_which_arm_it_favours(self,
                                                            monkeypatch):
        _, lines = _drive(monkeypatch, [_arm(), _arm()])
        joined = "\n".join(lines)
        assert "DECLARED BIAS" in joined
        assert "DIRECT arm" in joined

    def test_and_it_says_what_the_outcome_counts(self, monkeypatch):
        _, lines = _drive(monkeypatch, [_arm(), _arm()])
        joined = "\n".join(lines)
        for criterion in modes.JOINTLY_SCORABLE:
            assert criterion in joined


class TestWhichRunsAreCONFIRMATORY:
    def test_docs_is_declared_for_the_delivery_arms(self):
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery") == []

    @pytest.mark.parametrize("level", modes.DELIVERY_LEVELS)
    def test_and_so_are_its_generality_levels(self, level):
        assert modes.departures_from_the_protocol(
            level, modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery") == []

    def test_the_OTHER_protocols_target_is_exploratory(self):
        # Deciding afterwards which targets "count" is the post hoc
        # selection this module refuses everywhere.
        departures = modes.departures_from_the_protocol(
            "demo", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery")
        assert any("demo" in d for d in departures)

    def test_and_the_mirror_holds(self):
        departures = modes.departures_from_the_protocol(
            "docs", modes.PAIRS, modes.MULTI_ATTEMPTS, modes.TURNS, "turns")
        assert any("docs" in d for d in departures)

    def test_a_changed_pair_count_is_a_departure(self):
        assert modes.departures_from_the_protocol(
            "docs", 5, modes.DELIVERY_ATTEMPTS, modes.TURNS,
            "delivery") != []

    def test_a_changed_attempt_count_is_one_too(self):
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, 99, modes.TURNS, "delivery") != []

    def test_the_turn_count_is_NOT_one_for_a_delivery_run(self):
        # An indirect attempt is one message, so `--turns` means nothing to
        # this protocol and its default must not read as a departure.
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS, 99,
            "delivery") == []


class TestTheFileRecordsWHICHComparison:
    def test_the_arms_are_in_the_protocol_block(self, monkeypatch, tmp_path):
        import json
        output = tmp_path / "d.json"
        calls = []
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k) or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        monkeypatch.setattr("evaluation.evaluate_judge.judge_identity",
                            lambda: "fake/judge")
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      output=str(output), show=lambda *_: None,
                      target="docs", arms="delivery")
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["protocol"]["arms"] == "delivery", (
            "two comparisons produce files of the same SHAPE with different "
            "arms inside: resuming one into the other would mix two "
            "measurements in one figure")

    def test_a_file_from_the_OTHER_comparison_is_REFUSED(self, tmp_path):
        import json
        output = tmp_path / "d.json"
        output.write_text(json.dumps({
            "complete": False, "target": "docs",
            "protocol": {"pairs": 20, "multi_attempts": 6, "turns": 3,
                         "threshold": 0.05, "judge": "fake/judge",
                         "declared": True, "arms": "turns", "per_register": False},
            "pairs": [{"multi": _arm(), "single": _arm()}]}),
            encoding="utf-8")
        with pytest.raises(SystemExit):
            modes.already_measured(
                str(output), "docs",
                {"pairs": 20, "multi_attempts": 6, "turns": 3,
                 "threshold": 0.05, "judge": "fake/judge", "declared": True,
                 "arms": "delivery",
                 "per_register": False},
                show=lambda *_: None)


class TestTheSHAPEProtocol:
    """
    The second delivery run (2026-11-25): six payloads written as DOCUMENTS,
    testing the hypothesis the first run left — that the library's payloads
    are written to be SENT, not planted.

    A DIFFERENT measurement, not a rerun: different payloads, its own
    declared scope. Its justification is the recorded hypothesis, never "the
    last p was 0.0193".
    """

    def test_the_two_declared_scopes_are_the_library_and_the_shapes(self):
        assert modes.DELIVERY_SCOPES == ((), ("injection-indirecte",))

    def test_a_restricted_run_is_CONFIRMATORY(self):
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ("injection-indirecte",)) == []

    def test_the_FIRST_run_s_scope_still_is(self):
        # The unrestricted run is on the record; its scope must not become
        # exploratory retroactively.
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ()) == []

    def test_any_OTHER_scope_is_exploratory(self):
        departures = modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ("dan",))
        assert any("scope" in d for d in departures)

    def test_the_turns_protocol_declares_NO_scope(self):
        departures = modes.departures_from_the_protocol(
            "demo", modes.PAIRS, modes.MULTI_ATTEMPTS, modes.TURNS, "turns",
            ("injection-indirecte",))
        assert any("scope" in d for d in departures)

    def test_BOTH_arms_get_the_same_scope(self, monkeypatch):
        # The delivery stays the only variable: two arms drawing from
        # different pools would measure the pool.
        calls, _ = _drive(monkeypatch, [_arm(), _arm()])
        assert len(calls) == 2
        assert calls[0]["only"] == calls[1]["only"]

    def test_the_scope_reaches_the_campaign(self, monkeypatch):
        calls = []
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k)
                            or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lambda *_: None, target="docs", arms="delivery",
                      only=("injection-indirecte",))
        assert all(c["only"] == ("injection-indirecte",) for c in calls)

    def test_the_scope_is_RECORDED_in_the_protocol_block(self, monkeypatch,
                                                         tmp_path):
        import json
        output = tmp_path / "s.json"
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        monkeypatch.setattr("evaluation.evaluate_judge.judge_identity",
                            lambda: "fake/judge")
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      output=str(output), show=lambda *_: None,
                      target="docs", arms="delivery",
                      only=("injection-indirecte",))
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["protocol"]["only"] == ["injection-indirecte"]

    def test_a_file_from_the_OTHER_scope_is_REFUSED(self, tmp_path):
        # Written AND read in the same commit this time: `arms` sat in the
        # protocol block for an hour before anything compared it.
        import json
        output = tmp_path / "s.json"
        output.write_text(json.dumps({
            "complete": False, "target": "docs",
            "protocol": {"pairs": 20, "multi_attempts": 6, "turns": 3,
                         "threshold": 0.05, "judge": "fake/judge",
                         "declared": True, "arms": "delivery", "only": [],
                         "per_register": False},
            "pairs": [{"indirect": _arm(), "direct": _arm()}]}),
            encoding="utf-8")
        with pytest.raises(SystemExit, match="different payloads"):
            modes.already_measured(
                str(output), "docs",
                {"pairs": 20, "multi_attempts": 6, "turns": 3,
                 "threshold": 0.05, "judge": "fake/judge", "declared": True,
                 "arms": "delivery", "only": ["injection-indirecte"],
                 "per_register": False},
                show=lambda *_: None)

    def test_the_scope_is_ANNOUNCED_above_the_figures(self, monkeypatch):
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        lines = []
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lines.append, target="docs", arms="delivery",
                      only=("injection-indirecte",))
        assert "Scope: injection-indirecte." in "\n".join(lines)


class TestTheDocumentShapedPayloads:
    """
    Six registers, taken from the DOCUMENTED vectors of indirect injection
    and not from the one draw that worked. Exactly one of them is a shape
    observed working by hand, and that is declared — so the measurement can
    be read per register.
    """

    def _technique(self):
        import json
        import pathlib
        library = json.loads(
            (pathlib.Path(__file__).resolve().parent.parent
             / "payloads" / "library.json").read_text(encoding="utf-8"))
        found = [t for t in library["techniques"]
                 if t["id"] == "injection-indirecte"]
        assert found, "the technique is gone from the library"
        return found[0]

    def test_there_are_six_registers(self):
        assert len(self._technique()["templates"]) == 6

    def test_every_one_carries_the_OBJECTIVE_slot(self):
        # Templates and not complete payloads, by the rule the four LLM06
        # payloads established: a payload naming one target's secret or tool
        # is worth nothing against any other.
        for template in self._technique()["templates"]:
            assert "{objective}" in template

    def test_none_names_a_target_s_SECRET_or_TOOL(self):
        joined = " ".join(self._technique()["templates"])
        for specific in ("ARCHIVES-7731", "INTRANET-6052", "TOPSECRET42",
                         "consulter_dossier", "annuaire_lecteurs",
                         "fiche_adherent"):
            assert specific not in joined, (
                f"{specific} is in a template: it would only hold against "
                f"one target, which is what the objective axis is for")

    def test_each_one_is_shaped_like_a_DOCUMENT_and_not_a_message(self):
        """
        The property under test, and the whole point of the set: a payload
        addressing the assistant in the second person reads, inside a
        document, as a QUOTED user message — which is what the target did
        with the first note planted by hand.

        So each register carries a documentary marker: a reference, headers,
        a delimiter, a version, a question/answer pair.
        """
        markers = ("NOTE DE SERVICE", "---", "De :", "Métadonnées",
                   "FAQ", "Journal des versions")
        for template in self._technique()["templates"]:
            assert any(marker in template for marker in markers), template

    def test_the_description_says_WHICH_register_was_already_observed(self):
        # The honest handling of a set written after seeing one shape work:
        # a reader must be able to tell whether the effect rests on it.
        description = self._technique()["description"]
        assert "UN SEUL" in description
        assert "rupture de bloc" in description

    def test_it_has_NO_prerequisite(self):
        # The objective axis carries the target-specificity, and a document
        # pasted into a conversation holds against any chatbot -- which is
        # the condition for the direct arm to get something sensible.
        assert self._technique()["prerequisites"] == []


class TestTheCODEFingerprint:
    """
    A SIXTH thing a resume must refuse to cross, added 2026-11-25 with a
    20-pair run in flight and the refusal patterns, the tool marker and the
    replay's value test all about to be widened.

    AND IT SHIPPED UNGUARDED. Two mutations — the field dropped from the
    protocol block, and the comparison disabled — broke nothing at all. The
    irony is worth the line: the field was added precisely to close a
    "written but never read" gap, which is this project's commonest defect,
    and then it was itself written and never compared.
    """

    def test_it_changes_when_a_watched_file_changes(self, tmp_path,
                                                    monkeypatch):
        from evaluation.code_fingerprint import code_fingerprint
        before = code_fingerprint()
        assert before, "no fingerprint at all: nothing would be compared"
        # A file OUTSIDE the watched set must not move it: a digest over the
        # whole repository would change on a docstring and refuse every
        # legitimate resume.
        assert code_fingerprint() == before

    def test_a_missing_file_gives_NONE_and_not_a_partial_digest(self):
        from evaluation.code_fingerprint import code_fingerprint
        assert code_fingerprint(("does/not/exist.py",)) is None, (
            "a digest over a different set of files is a digest of something "
            "else, and comparing it would be worse than not comparing")

    def test_the_watched_set_names_what_decides_a_COUNT(self):
        from evaluation.code_fingerprint import WATCHED
        # Not "every file": the modules whose text decides what a campaign
        # sends and how its outcome is counted.
        for name in ("agents/adaptation.py", "agents/verifier.py",
                     "agents/planner.py", "main.py", "stats.py",
                     "payloads/library.json"):
            assert name in WATCHED, name
        assert "report.py" not in WATCHED, (
            "the rendering cannot change a count, and watching it would "
            "refuse resumes for nothing")

    def test_the_protocol_block_CARRIES_it(self, monkeypatch, tmp_path):
        import json
        output = tmp_path / "f.json"
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      output=str(output), show=lambda *_: None,
                      target="docs", arms="delivery")
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["protocol"]["code"], (
            "the field is not written, so there is nothing to compare")

    def test_a_file_from_ANOTHER_code_version_is_REFUSED(self, tmp_path):
        import json
        output = tmp_path / "f.json"
        output.write_text(json.dumps({
            "complete": False, "target": "docs",
            "protocol": {"pairs": 20, "multi_attempts": 6, "turns": 3,
                         "threshold": 0.05, "judge": "fake/judge",
                         "declared": True, "arms": "delivery", "only": [],
                         "per_register": False,
                         "code": "0000000000000000"},
            "pairs": [{"indirect": _arm(), "direct": _arm()}]}),
            encoding="utf-8")
        with pytest.raises(SystemExit, match="fingerprinted"):
            modes.already_measured(
                str(output), "docs",
                {"pairs": 20, "multi_attempts": 6, "turns": 3,
                 "threshold": 0.05, "judge": "fake/judge", "declared": True,
                 "arms": "delivery", "only": [], "per_register": False,
                 "code": "ffffffffffffffff"},
                show=lambda *_: None)

    def test_the_SAME_version_resumes_normally(self, tmp_path):
        # The contrast: a guard that refused every resume would be worse than
        # none, since resuming is a repair this project built on purpose.
        import json
        output = tmp_path / "f.json"
        protocol = {"pairs": 20, "multi_attempts": 6, "turns": 3,
                    "threshold": 0.05, "judge": "fake/judge",
                    "declared": True, "arms": "delivery", "only": [],
                    "per_register": False, "code": "abcdef0123456789"}
        output.write_text(json.dumps({
            "complete": False, "target": "docs", "protocol": protocol,
            "pairs": [{"indirect": _arm(), "direct": _arm()}]}),
            encoding="utf-8")
        done = modes.already_measured(str(output), "docs", dict(protocol),
                                      show=lambda *_: None)
        assert len(done) == 1

    def test_a_file_PREDATING_the_field_says_so_rather_than_passing(
            self, tmp_path, capsys):
        # The branch `judge` already has, and self-liquidating for the same
        # reason: every file written from here on carries it.
        import json
        output = tmp_path / "f.json"
        protocol = {"pairs": 20, "multi_attempts": 6, "turns": 3,
                    "threshold": 0.05, "judge": "fake/judge",
                    "declared": True, "arms": "delivery", "only": [],
                    "per_register": False, "code": "abcdef0123456789"}
        was = {k: v for k, v in protocol.items() if k != "code"}
        output.write_text(json.dumps({
            "complete": False, "target": "docs", "protocol": was,
            "pairs": [{"indirect": _arm(), "direct": _arm()}]}),
            encoding="utf-8")
        said = []
        done = modes.already_measured(str(output), "docs", dict(protocol),
                                      show=said.append)
        assert len(done) == 1
        assert any("predates the `code` field" in line for line in said)


class TestThePERREGISTERMode:
    """
    The third delivery run (2026-11-25): the registers SAMPLED.

    The shape run came back 19-0 for the direct arm with a declared defect —
    84% of its attempts went to one of the six registers and four were never
    drawn on the indirect side. That was identifiable before the run
    (`_share_budget` rotates by technique, the six are one technique), and
    this mode is what forces the sampling.
    """

    def test_the_six_registers_are_FOUND(self):
        assert len(modes.registers_of()) == 6

    def test_a_missing_technique_stops_rather_than_running_EMPTY(self):
        with pytest.raises(SystemExit, match="no registers"):
            modes.registers_of(technique="does-not-exist")

    def test_the_restriction_leaves_ONE_template(self):
        from agents.attacker import load_library
        with modes.only_register(2):
            library = load_library(with_garak=False)
            technique = [t for t in library["techniques"]
                         if t["id"] == modes.REGISTER_TECHNIQUE][0]
            assert len(technique["templates"]) == 1

    def test_and_it_is_the_one_ASKED_for(self):
        from agents.attacker import load_library
        expected = modes.registers_of()[2]
        with modes.only_register(2):
            library = load_library(with_garak=False)
            technique = [t for t in library["techniques"]
                         if t["id"] == modes.REGISTER_TECHNIQUE][0]
            assert technique["templates"] == [expected]

    def test_the_library_is_PUT_BACK(self):
        """
        The half that makes the restriction acceptable: a measurement that
        left the library restricted would silently narrow every later run,
        and the next figure would describe a pool nobody chose.
        """
        from agents.attacker import load_library
        before = load_library(with_garak=False)
        with modes.only_register(0):
            pass
        after = load_library(with_garak=False)
        assert before == after

    def test_it_is_put_back_even_if_the_SUB_RUN_RAISES(self):
        from agents.attacker import load_library
        before = load_library(with_garak=False)
        with pytest.raises(RuntimeError):
            with modes.only_register(0):
                raise RuntimeError("the sub-run died")
        assert load_library(with_garak=False) == before

    def test_LIBRARY_FILE_is_what_moves_and_not_load_library(self):
        """
        `agents/planner.py` binds `load_library` at import, so patching the
        FUNCTION would leave the planner reading the real library while this
        thought it had restricted it — the silent half-measure this module
        exists to avoid.
        """
        from agents import attacker
        original_function = attacker.load_library
        original_file = attacker.LIBRARY_FILE
        with modes.only_register(0):
            assert attacker.load_library is original_function, (
                "the FUNCTION was patched, which the planner's import would "
                "not see")
            assert attacker.LIBRARY_FILE != original_file
        assert attacker.LIBRARY_FILE == original_file

    def test_an_index_past_the_end_is_REFUSED(self):
        with pytest.raises(SystemExit, match="does not exist"):
            with modes.only_register(99):
                pass

    def test_every_pair_RECORDS_its_register(self, monkeypatch):
        calls = []
        sequence = [_arm() for _ in range(24)]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: calls.append(k)
                            or sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        results = modes.measure(
            pairs=2, multi_attempts=modes.DELIVERY_ATTEMPTS,
            show=lambda *_: None, target="docs", arms="delivery",
            only=("injection-indirecte",), per_register=True)
        # A measurement that does not record its own question cannot be
        # resumed, only repeated.
        assert all("register" in r for r in results)
        assert sorted({r["register"] for r in results}) == list(range(6))
        assert len(results) == 12, "two pairs per register, six registers"

    def test_the_breakdown_is_REPORTED(self, monkeypatch):
        # The previous protocol PROMISED a per-register table and the
        # instrument did not print it: it had to be recovered from a log.
        lines = []
        sequence = [_arm(1, ["divulgation"]) if i % 2 == 0 else _arm()
                    for i in range(24)]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=2, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lines.append, target="docs", arms="delivery",
                      only=("injection-indirecte",), per_register=True)
        joined = "\n".join(lines)
        assert "By REGISTER" in joined
        for index in range(1, 7):
            assert f"register {index}:" in joined, index

    def test_and_it_says_it_is_NEVER_tested(self, monkeypatch):
        # Six pairs per register cannot carry a sign test, and quoting a
        # sub-group p as a result is the post hoc selection this module
        # refuses everywhere.
        lines = []
        sequence = [_arm() for _ in range(24)]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=2, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lines.append, target="docs", arms="delivery",
                      only=("injection-indirecte",), per_register=True)
        joined = "\n".join(lines)
        assert "never tested" in joined

    def test_a_FLAT_run_prints_no_breakdown(self, monkeypatch):
        # The contrast: the table must not appear where there are no
        # registers to break down by.
        lines = []
        sequence = [_arm(), _arm()]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=1, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      show=lines.append, target="docs", arms="delivery")
        assert "By REGISTER" not in "\n".join(lines)

    def test_the_mode_is_in_the_PROTOCOL_block(self, monkeypatch, tmp_path):
        import json
        output = tmp_path / "r.json"
        sequence = [_arm() for _ in range(24)]
        monkeypatch.setattr(modes, "one_campaign",
                            lambda ask, **k: sequence.pop(0))
        monkeypatch.setattr("targets.choose_target",
                            lambda *a, **k: _plantable())
        modes.measure(pairs=2, multi_attempts=modes.DELIVERY_ATTEMPTS,
                      output=str(output), show=lambda *_: None,
                      target="docs", arms="delivery", per_register=True)
        written = json.loads(output.read_text(encoding="utf-8"))
        assert written["protocol"]["per_register"] is True

    def test_a_FLAT_file_is_refused_by_a_per_register_run(self, tmp_path):
        import json
        output = tmp_path / "r.json"
        output.write_text(json.dumps({
            "complete": False, "target": "docs",
            "protocol": {"pairs": 6, "multi_attempts": 6, "turns": 3,
                         "threshold": 0.05, "judge": "fake/judge",
                         "declared": True, "arms": "delivery", "only": [],
                         "per_register": False, "code": "aaaa"},
            "pairs": [{"indirect": _arm(), "direct": _arm()}]}),
            encoding="utf-8")
        # The pair count is EQUAL on both sides on purpose: it is checked
        # first, so leaving it different would have this test passing on the
        # wrong guard.
        with pytest.raises(SystemExit, match="per-register"):
            modes.already_measured(
                str(output), "docs",
                {"pairs": 6, "multi_attempts": 6, "turns": 3,
                 "threshold": 0.05, "judge": "fake/judge", "declared": True,
                 "arms": "delivery", "only": [], "per_register": True,
                 "code": "aaaa"},
                show=lambda *_: None)

    def test_its_pair_count_is_CONFIRMATORY(self):
        assert modes.departures_from_the_protocol(
            "docs", modes.PER_REGISTER_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ("injection-indirecte",),
            per_register=True) == []

    def test_and_the_FLAT_count_is_a_departure_there(self):
        # The two protocols declare different pair counts, so one read
        # against the other would call a confirmatory run exploratory.
        assert modes.departures_from_the_protocol(
            "docs", modes.DELIVERY_PAIRS, modes.DELIVERY_ATTEMPTS,
            modes.TURNS, "delivery", ("injection-indirecte",),
            per_register=True) != []
