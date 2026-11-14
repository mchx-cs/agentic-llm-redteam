"""
Tests for the campaign budget.

The budget is a CIRCUIT BREAKER, not an economy: at the current scale a
campaign costs pennies. What it stops is the loop that runs away.

Two properties matter, and the second more than the first:
1. the cap really is applied;
2. the stop is CLEAN — a campaign cut short must never present itself as a
   finished campaign, otherwise "no finding" would suggest a coverage that
   never happened.
"""

import pytest

import llm_client
from llm_client import (BudgetExceeded, ask_llm, call_log,
                        reset_call_log)
from rapport import build_report, render_markdown


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    """A model that answers instantly, with no network and no quota."""
    class _Usage:
        total_tokens = 100

    class _Choice:
        finish_reason = "stop"
        message = type("M", (), {"content": "réponse"})()

    class _Reply:
        usage = _Usage()
        choices = [_Choice()]

    class _Client:
        chat = type("C", (), {"completions": type("D", (), {
            "create": staticmethod(lambda **k: _Reply())})()})()

    monkeypatch.setattr(llm_client, "_client_for", lambda profile: _Client())
    yield
    reset_call_log()  # we leave no cap armed behind us


class TestCallCap:
    def test_the_cap_is_applied(self):
        reset_call_log(max_calls=3)
        for _ in range(3):
            ask_llm("x")
        with pytest.raises(BudgetExceeded, match="3 appel"):
            ask_llm("x")

    def test_the_message_says_the_count_and_the_cap(self):
        reset_call_log(max_calls=1)
        ask_llm("x")
        with pytest.raises(BudgetExceeded, match="plafond 1"):
            ask_llm("x")


class TestTokenCap:
    def test_the_cap_is_applied(self):
        # Each fake call costs 100 tokens.
        reset_call_log(max_tokens=250)
        for _ in range(3):           # 300 tokens consumed
            ask_llm("x")
        with pytest.raises(BudgetExceeded, match="tokens"):
            ask_llm("x")

    def test_the_overshoot_is_bounded_to_one_call(self):
        # A call's cost is only known afterwards: we check what has ALREADY
        # been consumed, so we can overshoot by one call, never more.
        reset_call_log(max_tokens=250)
        for _ in range(3):
            ask_llm("x")
        assert call_log()["tokens"] == 300
        with pytest.raises(BudgetExceeded):
            ask_llm("x")
        assert call_log()["tokens"] == 300  # the refused call cost nothing


class TestWithoutACap:
    def test_by_default_nothing_is_limited(self):
        # The evaluation scripts consume far more than a campaign and have no
        # reason to be cut off in the middle of a measurement.
        reset_call_log()
        for _ in range(50):
            ask_llm("x")
        assert call_log()["appels"] == 50

    def test_resetting_disarms_the_cap(self):
        reset_call_log(max_calls=1)
        ask_llm("x")
        reset_call_log()
        ask_llm("x")          # must no longer raise
        assert call_log()["appels"] == 1


class TestCleanStop:
    def test_the_budget_is_not_a_failure(self):
        # Telling the two apart is what lets the orchestrator conclude "cut
        # short" instead of "crashed".
        assert issubclass(BudgetExceeded, RuntimeError)

    def test_the_report_announces_a_campaign_cut_short(self):
        result = {
            "statut": "budget_epuise", "fiche": None,
            "plan": {"essais": [{"technique": "t", "famille_owasp": "LLM01",
                                 "objectif": "o", "transformation": "identite",
                                 "texte": "p"}], "ecartees": []},
            "constats": [], "ecourtee": "Budget atteint : 6 appel(s).",
            "journal": {"appels": 6, "tokens": 100, "tronquees": []},
        }
        text = render_markdown(build_report(result, target="essai"))
        assert "ÉCOURTÉE" in text
        # And above all: the coverage must denounce itself.
        assert "incomplète" in text

    def test_a_complete_campaign_carries_no_warning(self):
        result = {
            "statut": "aucun_constat", "fiche": None,
            "plan": {"essais": [], "ecartees": []}, "constats": [],
            "ecourtee": None, "journal": {},
        }
        text = render_markdown(build_report(result, target="essai"))
        assert "ÉCOURTÉE" not in text
