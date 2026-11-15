"""
Tests for the labelling tool — the one file in `evaluation/` that had none.

Why it had none: `evaluation/` holds the measurements that NEED a model, and
`tests/` must never call one. But `label.py` calls no model at all. It
reads two JSON working files, asks the author questions, and writes a corpus.
Its interactive half cannot be tested without faking a terminal; its
INTEGRATION half can, and that is the half that touches the ground truth.

The gap cost a real defect, found by reading the file rather than by running
it: `integrate()` ended on `restants`, a local of `label()`, so the command
raised a NameError on its very last line — after having written the corpus.
The data survived, the closing message did not, and nothing reported it.
"""

import json

import pytest

from evaluation import label


def _entry(identifier, group, expected=True, dataset="dev"):
    return {"id": identifier, "group": group, "category": "controle",
            "dataset": dataset, "secret": "TOPSECRET42", "source": "attempt",
            "payload": "p", "reply": "r", "expected": expected,
            "trap": "x"}


@pytest.fixture
def harvests(tmp_path, monkeypatch):
    """Two working files and an empty corpus, all inside tmp_path."""
    to_label = tmp_path / "to_label.json"
    conversations = tmp_path / "to_label_conversations.json"
    corpus = tmp_path / "labelled_exchanges.json"
    corpus.write_text(json.dumps({"exchanges": []}), encoding="utf-8")

    monkeypatch.setattr(label, "TO_LABEL_FILE", to_label)
    monkeypatch.setattr(label, "CONVERSATIONS_FILE", conversations)
    monkeypatch.setattr(label, "CORPUS_FILE", corpus)
    monkeypatch.setattr(label, "SOURCES",
                        ((to_label, "exchanges"),
                         (conversations, "conversations")))
    return {"to_label": to_label, "conversations": conversations,
            "corpus": corpus}


class TestIntegration:
    def test_a_labelled_exchange_joins_the_corpus(self, harvests, capsys):
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01")]}),
            encoding="utf-8")
        label.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert [e["id"] for e in corpus["exchanges"]] == ["R01-1"]
        # And the harvest keeps only what is left to label: nothing here.
        left = json.loads(harvests["to_label"].read_text(encoding="utf-8"))
        assert left["exchanges"] == []

    def test_integrate_runs_to_the_end(self, harvests, capsys):
        """
        THE test that was missing. `integrate()` must RETURN, not raise: its
        last line named a variable belonging to another function, and the
        corpus was written before it broke. A defect silent for the data,
        loud for the operator, and covered by nothing.
        """
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01"),
                                     _entry("R02-1", "R02", expected=None)]}),
            encoding="utf-8")
        label.integrate()                      # must not raise
        output = capsys.readouterr().out
        assert "1 exchange(s) added" in output
        # And the count of what is left is RIGHT: the unlabelled entry.
        assert "1 exchange(s) left to label" in output

    def test_nothing_to_integrate_leaves_the_corpus_alone(self, harvests):
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01", expected=None)]}),
            encoding="utf-8")
        label.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert corpus["exchanges"] == []

    def test_a_group_is_not_split_between_the_sets(self, harvests, capsys):
        """
        The guard that matters: the frozen set must never receive the
        rewording of a case the judge was tuned on.
        """
        harvests["corpus"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01", dataset="dev")]}),
            encoding="utf-8")
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [_entry("R01-2", "R01", dataset="test")]}),
            encoding="utf-8")
        label.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert [e["id"] for e in corpus["exchanges"]] == ["R01-1"]
        assert "Skipped" in capsys.readouterr().out

    def test_a_conversation_is_flagged_as_not_measured(self, harvests,
                                                       capsys):
        """
        A corpus that grows without the measurement changing needs explaining.
        """
        conversation = _entry("C-01-1", "C-01")
        conversation["turns"] = [{"role": "attacker", "content": "a"},
                                 {"role": "target", "content": "b"}]
        harvests["conversations"].write_text(
            json.dumps({"conversations": [conversation]}), encoding="utf-8")
        label.integrate()
        assert "are NOT measured yet" in capsys.readouterr().out


class TestWhatIsLeftToLabel:
    def test_it_counts_both_harvests(self, harvests):
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01", expected=None)]}),
            encoding="utf-8")
        harvests["conversations"].write_text(
            json.dumps({"conversations": [
                _entry("C-01-1", "C-01", expected=None)]}),
            encoding="utf-8")
        assert label._left_to_label(label._harvests()) == 2

    def test_a_missing_harvest_is_not_an_error(self, harvests):
        assert label._harvests() == []
        assert label._left_to_label([]) == 0


class TestTheCheck:
    """
    `--check` reports, never corrects, and every check it makes is arithmetic
    or a string search. It exists because `--integrate` refuses a split group
    but says nothing about the rest, and because a labelling session runs over
    several evenings: a slip made on Monday is cheaper to find on Tuesday than
    after it has gone into the corpus.
    """

    @staticmethod
    def _write(harvests, entries):
        harvests["conversations"].write_text(
            json.dumps({"conversations": entries}), encoding="utf-8")

    def test_a_clean_labelling_reports_nothing(self, harvests, capsys):
        entry = _entry("R01-1", "R01")
        entry["breach_turn"] = 1
        self._write(harvests, [entry])
        assert label.check() == 0
        assert "Nothing to report" in capsys.readouterr().out

    def test_a_group_split_between_the_sets_is_a_problem(self, harvests,
                                                         capsys):
        """
        The leak that would make the frozen set worthless: it would hold a
        rewording of a case the judge was tuned on.
        """
        a = _entry("R01-1", "R01", dataset="dev")
        b = _entry("R01-2", "R01", dataset="test")
        a["breach_turn"] = b["breach_turn"] = 1
        self._write(harvests, [a, b])
        assert label.check() == 1
        assert "is in both 'dev' and 'test'" in capsys.readouterr().out

    def test_a_vulnerability_with_no_turn_is_a_problem(self, harvests,
                                                      capsys):
        entry = _entry("R01-1", "R01", expected=True)
        entry["breach_turn"] = None
        self._write(harvests, [entry])
        assert label.check() == 1
        assert "a vulnerability with no turn" in capsys.readouterr().out

    def test_a_negative_that_names_a_turn_is_a_problem(self, harvests,
                                                       capsys):
        entry = _entry("R01-1", "R01", expected=False)
        entry["breach_turn"] = 2
        self._write(harvests, [entry])
        assert label.check() == 1
        assert "no vulnerability, but turn 2 is named" in \
            capsys.readouterr().out

    def test_a_turn_beyond_the_conversation_is_a_problem(self, harvests,
                                                         capsys):
        entry = _entry("C01-1", "C01", expected=True)
        entry.pop("payload"), entry.pop("reply")
        entry["turns"] = [{"role": "attacker", "content": "a"},
                          {"role": "target", "content": "b"}]
        entry["breach_turn"] = 3
        self._write(harvests, [entry])
        assert label.check() == 1
        assert "turn 3 but the exchange has 1" in capsys.readouterr().out

    def test_an_invented_category_is_a_problem(self, harvests, capsys):
        # A synonym would stop the errors being groupable by kind of trap,
        # which is the whole reason the category list is offered as a menu.
        entry = _entry("R01-1", "R01")
        entry["category"] = "fuite_directe"      # underscore, not hyphen
        entry["breach_turn"] = 1
        self._write(harvests, [entry])
        assert label.check() == 1
        assert "unknown category" in capsys.readouterr().out

    def test_a_leak_category_with_no_secret_in_the_reply_is_a_QUESTION(
            self, harvests, capsys):
        """
        Reported with a `?`, not a `!`, and the exit code stays 0. A leak can
        be paraphrased; this is the one place a label meets a mechanical fact,
        and it must not pretend to overrule the author.
        """
        entry = _entry("R01-1", "R01")
        entry["category"] = "fuite-directe"
        entry["secret"] = "ARCHIVES-7731"
        entry["reply"] = "Je ne peux pas vous le dire."
        entry["breach_turn"] = 1
        self._write(harvests, [entry])
        assert label.check() == 0
        out = capsys.readouterr().out
        assert "worth a second look" in out
        assert "secret string is in no chatbot turn" in out

    def test_the_categories_used_are_listed(self, harvests, capsys):
        # So a drift towards a near-synonym is visible across a session.
        entry = _entry("R01-1", "R01")
        entry["breach_turn"] = 1
        self._write(harvests, [entry])
        label.check()
        assert "Categories used" in capsys.readouterr().out
