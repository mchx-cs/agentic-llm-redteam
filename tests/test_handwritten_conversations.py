"""
Tests for the hand-written conversations (phase 3b).

No LLM call. What is checked here is not a model's behaviour but properties
of the CORPUS — and they are what makes a measurement mean something.
"""

import pytest

from evaluation.handwritten_conversations import CASES, SECRET, entries


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.reconnaissance", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse,
                            raising=False)


class TestGroundTruth:
    """
    The labels are the ground truth, and it is the AUTHOR who validates them.
    This file writes SCENARIOS, not verdicts — a test guarantees it, because
    that is the rule easiest to break out of convenience.
    """

    def test_a_single_turn_case_comes_out_single_turn(self):
        # Otherwise `evaluate_judge` would skip it, while the judge reads
        # it perfectly well: a one-turn exchange dressed up as a conversation
        # would be lost to a measurement it can feed.
        for entry in entries():
            if entry["format"] == "mono-tour":
                assert "payload" in entry and "reply" in entry
                assert "turns" not in entry
            else:
                assert "turns" in entry and len(entry["turns"]) > 2

    def test_no_verdict_is_pre_filled(self):
        for entry in entries():
            assert entry["expected"] is None, entry["id"]
            assert entry["category"] is None, entry["id"]
            assert entry["dataset"] is None, entry["id"]

    def test_every_case_says_WHY_it_exists(self):
        # Without the intention, the author gets two nearly identical
        # conversations with no idea why both are being shown.
        for entry in entries():
            assert len(entry["trap"]) > 60, entry["id"]


class TestThePairsReallyArePairs:
    """
    The lesson of D13/D14: a negative case on its own teaches the judge too
    broad a rule. It needs its positive twin, with nearly identical text.
    """

    def _by_group(self):
        groups = {}
        for identifier, group, _, turns in CASES:
            groups.setdefault(group, []).append((identifier, turns))
        return groups

    def _pairs(self):
        """
        Every group holding exactly two cases IS a pair, by construction.

        Derived rather than listed, after the previous version named its two
        groups in the source: adding `A-echo` on 2026-11-16 left it passing
        while guarding nothing, the same defect as a test comparing a result
        to the constant that produced it.
        """
        return {g: members for g, members in self._by_group().items()
                if len(members) == 2}

    def test_there_ARE_pairs_and_they_share_their_group(self):
        # Sharing a group means sharing a SET: the judge cannot be tuned on
        # one twin and measured on the other.
        pairs = self._pairs()
        assert len(pairs) >= 3, (
            f"only {len(pairs)} pair(s): the D13/D14 lesson needs at least "
            f"the secret asserted, the secret confirmed and the secret "
            f"echoed")
        assert "A-secret-attaquant" in pairs and "A-confirmation" in pairs

    def test_the_twins_differ_only_by_the_REPLY(self):
        # The discriminant must be what the TARGET says, not what the
        # attacker asks: otherwise the case measures something else.
        for group in self._pairs():
            (_, first), (_, second) = self._by_group()[group]
            requests_1 = [t["content"] for t in first
                          if t["role"] == "attacker"]
            requests_2 = [t["content"] for t in second
                          if t["role"] == "attacker"]
            assert requests_1 == requests_2, group
            replies_1 = [t["content"] for t in first
                          if t["role"] == "target"]
            replies_2 = [t["content"] for t in second
                          if t["role"] == "target"]
            assert replies_1 != replies_2, group


class TestTheUnreachableTrapsAreCovered:
    def test_the_secret_appears_in_an_ATTACKER_turn(self):
        # The false positive specific to multi-turn. No harvest can produce
        # it: our payloads look for the secret, they do not contain it.
        attacker = [t for _, _, _, turns in CASES for t in turns
                     if t["role"] == "attacker" and SECRET in t["content"]]
        assert attacker, "aucun cas ne met le secret dans la bouche de l'attaquant"

    def test_one_case_leaks_on_an_EARLIER_turn(self):
        # 7 leaks out of 11 had this shape in the real harvest.
        found = False
        for _, _, _, turns in CASES:
            replies = [t["content"] for t in turns if t["role"] == "target"]
            if len(replies) >= 2 and SECRET in replies[0] \
                    and SECRET not in replies[-1]:
                found = True
        assert found

    def test_some_conversations_exceed_two_turns(self):
        # `sequence_turns()` produces only two: beyond that, by hand.
        assert any(len(turns) // 2 > 2 for _, _, _, turns in CASES)

    def test_there_are_entirely_harmless_controls(self):
        # Without them, false positives would be zero by construction.
        harmless = [turns for _, _, _, turns in CASES
                   if not any(SECRET in t["content"] for t in turns)
                   and "instructions" not in turns[0]["content"].lower()]
        assert harmless

    def test_the_turns_always_alternate(self):
        # A malformed corpus would have an incoherent dialogue scored.
        for identifier, _, _, turns in CASES:
            roles = [t["role"] for t in turns]
            assert roles == ["attacker", "target"] * (len(roles) // 2), \
                identifier


class TestPouringIn:
    def test_pouring_in_does_not_overwrite_the_harvest(self, monkeypatch, tmp_path):
        import evaluation.handwritten_conversations as by_hand
        import json

        harvest = tmp_path / "recolte.json"
        harvest.write_text(json.dumps({"conversations": [
            {"id": "C-demo-01-1", "expected": None}]}), encoding="utf-8")
        monkeypatch.setattr(by_hand, "HARVEST_FILE", harvest)

        added, total = by_hand.add_to_harvest()
        assert len(added) == len(CASES)
        assert total == len(CASES) + 1

    def test_pouring_in_twice_duplicates_nothing(self, monkeypatch, tmp_path):
        import evaluation.handwritten_conversations as by_hand

        monkeypatch.setattr(by_hand, "HARVEST_FILE",
                            tmp_path / "recolte.json")
        by_hand.add_to_harvest()
        added, total = by_hand.add_to_harvest()
        assert added == []
        assert total == len(CASES)
