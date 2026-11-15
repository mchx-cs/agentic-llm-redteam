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
    return {"a_etiqueter": to_label, "conversations": conversations,
            "corpus": corpus}


class TestIntegration:
    def test_a_labelled_exchange_joins_the_corpus(self, harvests, capsys):
        harvests["a_etiqueter"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01")]}),
            encoding="utf-8")
        label.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert [e["id"] for e in corpus["exchanges"]] == ["R01-1"]
        # And the harvest keeps only what is left to label: nothing here.
        left = json.loads(harvests["a_etiqueter"].read_text(encoding="utf-8"))
        assert left["exchanges"] == []

    def test_integrate_runs_to_the_end(self, harvests, capsys):
        """
        THE test that was missing. `integrate()` must RETURN, not raise: its
        last line named a variable belonging to another function, and the
        corpus was written before it broke. A defect silent for the data,
        loud for the operator, and covered by nothing.
        """
        harvests["a_etiqueter"].write_text(
            json.dumps({"exchanges": [_entry("R01-1", "R01"),
                                     _entry("R02-1", "R02", expected=None)]}),
            encoding="utf-8")
        label.integrate()                      # must not raise
        output = capsys.readouterr().out
        assert "1 exchange(s) added" in output
        # And the count of what is left is RIGHT: the unlabelled entry.
        assert "1 exchange(s) left to label" in output

    def test_nothing_to_integrate_leaves_the_corpus_alone(self, harvests):
        harvests["a_etiqueter"].write_text(
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
        harvests["a_etiqueter"].write_text(
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
        harvests["a_etiqueter"].write_text(
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
