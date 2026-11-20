"""
Tests for pass@k — `--repeat` (2026-11-20).

The last piece of phase 13, and the reason the bounded null could not be
produced honestly on 2026-11-19: the report advised
`--only <technique> --no-adaptation` as giving independent attempts, and a
30-attempt run of it spans FOUR objectives. `stats.py` names that as
heterogeneity in its own docstring ("different probes, from different
families, **against different objectives**"), so the gate called four
different Bernoulli variables independent and would have printed a bound over
them.

No LLM call: the planner is driven on a hand-made profile and library, and
`run_campaign` on a deterministic target.
"""

import pytest

import main
from agents.planner import plan_campaign


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge", "agents.reconnaissance"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


@pytest.fixture(autouse=True)
def no_garak(monkeypatch, tmp_path):
    """The pool must be KNOWN, never whatever a local snapshot happens to be."""
    monkeypatch.setenv("GARAK_FILE", str(tmp_path / "absent.json"))


# The real profile shape, taken from the one `tests/test_planner.py` uses
# rather than invented: `writes_code` and `handles_documents` are TRI-STATES,
# and None is "the target said nothing", not "it cannot".
PROFILE = {"role": "assistant", "language": "fr", "tools": ["consulter"],
           "refused_subjects": ["le code du fonds ancien", "les dossiers"],
           "mentions_instructions": True,
           "writes_code": None, "handles_documents": None, "context": [],
           "evidence": [], "exchanges": [], "warning": None}


def _plan(budget, repeat=False, only=("fuite-prompt-systeme",)):
    return plan_campaign(PROFILE, budget, only=only, repeat=repeat)


class TestASweepIsNotIID:
    """
    The measurement that forced this work, reproduced as a test so the claim
    stops depending on a campaign anyone has to re-run.
    """

    def test_one_technique_still_crosses_SEVERAL_combinations(self):
        attempts = _plan(30)["attempts"]
        assert len(attempts) > 1
        triples = {(a["technique"], a["objective"], a["transformation"])
                   for a in attempts}
        assert len(triples) > 1, (
            "a sweep over ONE technique still varies the objective and the "
            "transformation, so its attempts are not trials of one Bernoulli "
            "variable — which is exactly what stats.py calls heterogeneous")


class TestRepeatBuildsAPoolOfONE:
    def test_every_attempt_is_the_same_combination(self):
        plan = _plan(12, repeat=True)
        triples = {(a["technique"], a["objective"], a["transformation"])
                   for a in plan["attempts"]}
        assert len(triples) == 1

    def test_there_are_exactly_BUDGET_of_them(self):
        assert len(_plan(7, repeat=True)["attempts"]) == 7

    def test_the_pool_holds_nothing_else(self):
        """
        `candidates` is normally the untruncated pool, because a relegated
        attempt must be able to climb back. Under `repeat` there is nothing to
        climb over, and leaving the others in would let the campaign wander
        off the one combination it was told to measure.
        """
        plan = _plan(5, repeat=True)
        assert plan["candidates"] == plan["attempts"]

    def test_the_combination_is_the_POOLS_OWN_HEAD(self):
        # Not a second selection rule nobody can audit: the planner's
        # priority order already decides, and `--only` is how an operator
        # pins what they want measured.
        swept = _plan(30)
        repeated = _plan(30, repeat=True)["attempts"][0]
        best = min(swept["candidates"], key=lambda a: a["priority"])
        assert (repeated["technique"], repeated["objective"],
                repeated["transformation"]) == (
            best["technique"], best["objective"], best["transformation"])

    def test_the_attempts_are_DISTINCT_dicts(self):
        # The campaign stamps adaptation reasons on what it draws; one shared
        # dict would carry every turn's annotations into all the others.
        attempts = _plan(4, repeat=True)["attempts"]
        attempts[0]["adaptation_reasons"] = ["marker"]
        assert "adaptation_reasons" not in attempts[1]

    def test_WHAT_was_repeated_is_recorded(self):
        # The bound's justification has to live in the document that prints
        # the bound.
        plan = _plan(3, repeat=True)
        assert set(plan["repeated"]) == {"technique", "objective",
                                         "transformation"}
        assert plan["repeated"]["technique"] == plan["attempts"][0]["technique"]

    def test_a_sweep_records_NOTHING(self):
        assert "repeated" not in _plan(3)

    def test_an_empty_pool_stays_empty(self):
        # Nothing to repeat, and no crash on `attempts[0]`: a scope that keeps
        # nothing must still produce the "no attempt applies" path.
        plan = _plan(5, repeat=True, only=("technique-qui-nexiste-pas",))
        assert plan["attempts"] == []


class TestTheCampaignREALLYSendsItNTimes:
    """
    The planner building a pool of one is half of it. `next_attempt` excludes
    by TEXT — which is what stops a sweep repeating a payload — so without
    the loop's half the campaign would send it once and then find the pool
    exhausted.
    """

    @staticmethod
    def _run(monkeypatch, **kwargs):
        sent = []

        def target(message, history=None):
            sent.append(message)
            return "Je ne peux pas vous aider."

        monkeypatch.setattr(main, "reconnoitre", lambda *a, **k: PROFILE)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda *a, **k: {"reussi": False,
                                             "critere": "aucun",
                                             "analyse": "refus",
                                             "votes": [False, False, False]})
        result = main.run_campaign(
            ask_target=target, target_name="mock", adaptive=False,
            only=("fuite-prompt-systeme",), **kwargs)
        return result, sent

    def test_eight_attempts_means_eight_sends_of_one_text(self, monkeypatch):
        result, sent = self._run(monkeypatch, attempts=8, repeat=True)
        assert len(sent) == 8, (
            "next_attempt excludes what was already sent, so pass@k needs "
            "the loop to stop counting its own repetition as exhaustion")
        assert len(set(sent)) == 1

    def test_and_the_gate_then_says_INDEPENDENT(self, monkeypatch):
        result, _ = self._run(monkeypatch, attempts=8, repeat=True)
        assert result["independent_attempts"] is True

    def test_a_sweep_of_the_same_technique_does_NOT(self, monkeypatch):
        # The defect this work fixes, as a test: one technique, no
        # adaptation, and the gate must refuse the bound because the
        # objectives differ.
        result, sent = self._run(monkeypatch, attempts=8)
        assert len(set(sent)) > 1
        assert result["independent_attempts"] is False

    def test_adaptation_still_forbids_the_bound(self, monkeypatch):
        """
        `--repeat` makes the attempts identical, so adaptation can change
        nothing — but the gate checks the FACTS and not the intention, and a
        campaign that learned from its replies is not one whose attempts were
        independent. Over-strict here, and that is the safe direction.
        """
        sent = []
        monkeypatch.setattr(main, "reconnoitre", lambda *a, **k: PROFILE)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda *a, **k: {"reussi": False,
                                             "critere": "aucun",
                                             "analyse": "r",
                                             "votes": [False] * 3})
        result = main.run_campaign(
            ask_target=lambda m, history=None: sent.append(m) or "non",
            target_name="mock", adaptive=True, repeat=True, attempts=4,
            only=("fuite-prompt-systeme",))
        assert result["independent_attempts"] is False


class TestWhatTheREPORTThenSays:
    def test_the_bound_NAMES_the_combination(self, monkeypatch):
        import report

        sent = []
        monkeypatch.setattr(main, "reconnoitre", lambda *a, **k: PROFILE)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda *a, **k: {"reussi": False,
                                             "critere": "aucun",
                                             "analyse": "r",
                                             "votes": [False] * 3})
        result = main.run_campaign(
            ask_target=lambda m, history=None: sent.append(m) or "non",
            target_name="mock", adaptive=False, repeat=True, attempts=30,
            only=("fuite-prompt-systeme",))

        built = report.build_report(result, target="mock")
        assert built["repeated"] is not None
        rendered = report.render_markdown(built)
        assert "the SAME combination" in rendered, (
            "'one technique' overstated the gate: a sweep over one technique "
            "is not i.i.d., and the sentence has to say what actually was")
        assert built["repeated"]["technique"] in rendered
        assert "30" in rendered

    def test_a_sweep_gets_no_bound_and_no_name(self, monkeypatch):
        import report

        monkeypatch.setattr(main, "reconnoitre", lambda *a, **k: PROFILE)
        monkeypatch.setattr(main, "judge_by_vote",
                            lambda *a, **k: {"reussi": False,
                                             "critere": "aucun",
                                             "analyse": "r",
                                             "votes": [False] * 3})
        result = main.run_campaign(
            ask_target=lambda m, history=None: "non",
            target_name="mock", adaptive=False, attempts=6,
            only=("fuite-prompt-systeme",))
        built = report.build_report(result, target="mock")
        assert built["repeated"] is None
        rendered = report.render_markdown(built)
        assert "No numerical bound is given" in rendered


class TestAnIIDRunWithFindingsMEASURESTheRate:
    """
    `stats.summarise` gives a Wilson interval for successes > 0 too, and the
    bounds block read it only in its no-finding branch — so the interval was
    computed, stored in `result.json` and printed nowhere. A field written and
    never read, like phase 14's three chain-of-custody fields.

    And the sentence it left standing was false in that case: "it does not say
    how often" is true of a sweep and wrong of a repetition, which measures
    exactly that.
    """

    @staticmethod
    def _rendered(successes, attempts, independent, repeated=None):
        import report
        import stats

        bounds = stats.summarise(successes, attempts, independent=independent,
                                 what="attempts of the same combination")
        return "\n".join(report._bounds_block(
            bounds, successes, rate=None, repeated=repeated))

    def test_the_interval_is_PRINTED(self):
        text = self._rendered(16, 30, independent=True)
        assert "says how often" in text
        assert "It does not say how often" not in text, (
            "a claim followed two lines later by its retraction is the "
            "contradiction the Coverage section was corrected for: the "
            "sentence is CHOSEN, not contradicted")
        assert "between 36% and 70%" in text, (
            "16 of 30 reads as 53%, and thirty trials support 36%-70%: the "
            "range is the claim, the point is not")

    def test_it_NAMES_the_combination_it_measured(self):
        text = self._rendered(
            16, 30, independent=True,
            repeated={"technique": "fuite-prompt-systeme",
                      "objective": "refus-1", "transformation": "identity"})
        assert "fuite-prompt-systeme" in text and "refus-1" in text

    def test_a_SWEEP_with_findings_still_says_it_does_not_know(self):
        # The contrast that makes the addition mean something: a sweep's
        # attempts are different payloads, so it genuinely cannot say how
        # often, and claiming a rate there would be the unjustified bound
        # stats.py exists to refuse.
        text = self._rendered(16, 30, independent=False)
        assert "It does not say how often" in text
        assert "But here it does" not in text

    def test_a_ZERO_still_takes_the_other_branch(self):
        text = self._rendered(0, 30, independent=True)
        assert "does not demonstrate that the target is secure" in text
        assert "But here it does" not in text
