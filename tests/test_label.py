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

    @staticmethod
    def _integrate_with(harvests, turns):
        conversation = _entry("C-01-1", "C-01")
        conversation["turns"] = turns
        harvests["conversations"].write_text(
            json.dumps({"conversations": [conversation]}), encoding="utf-8")
        label.integrate()

    def test_a_conversation_is_flagged_as_judged_on_its_OWN_line(
            self, harvests, capsys):
        """
        This test previously asserted "are NOT measured yet", and it was
        right when it was written. It changed because the BEHAVIOUR improved:
        the multi-turn instruction landed, `evaluate_judge` judges
        conversations with `judge_conversation` and reports them separately.
        Left as it was, it would have kept telling the author that the cases
        they just integrated enter no measurement.

        What has to be said instead is what the figure MEANS: the two formats
        are never pooled, so a conversation does not move the single-turn
        line the published 89 / 100 / 96 is compared against.
        """
        self._integrate_with(harvests, [
            {"role": "attacker", "content": "a"},
            {"role": "target", "content": "b"},
            {"role": "attacker", "content": "c"},
            {"role": "target", "content": "d"}])
        out = capsys.readouterr().out
        assert "never pooled" in out
        assert "NOT measured" not in out, (
            "the old message said conversations are not measured; they are")

    def test_a_SINGLE_exchange_stored_as_turns_is_not_one(self, harvests,
                                                          capsys):
        """
        The count must come from `is_conversation`, not from "does it carry
        turns". Two hand-written entries (A03, A04) are single-turn exchanges
        living in the conversations harvest -- exactly the case a
        `turns`-based count gets wrong, and the reason that function exists.

        Counting the other way reported 120 conversations on 2026-11-16 where
        64 would be judged as such: a number no measurement would ever use.
        """
        self._integrate_with(harvests, [
            {"role": "attacker", "content": "a"},
            {"role": "target", "content": "b"}])
        out = capsys.readouterr().out
        assert "0 of them conversation" in out, out
        assert "never pooled" not in out, (
            "a single exchange was announced as a conversation")


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


class TestLabellingNamedEntries:
    """
    `--ids`, the gesture `--revise` already offered for the CORPUS.

    Without it, labelling three new hand-written cases meant walking the
    18,515 unlabelled entries an unbounded `collect_exchanges` sweep had
    left in `to_label.json`. The three were real work; the 18,515 were not
    asked for.
    """

    @staticmethod
    def _harvest(harvests, ids):
        entries = []
        for identifier in ids:
            entry = _entry(identifier, f"G-{identifier}")
            entry["expected"] = None
            entry["dataset"] = None
            entries.append(entry)
        harvests["conversations"].write_text(
            json.dumps({"conversations": entries}), encoding="utf-8")

    @staticmethod
    def _answers(monkeypatch, answers):
        supplied = iter(answers)
        monkeypatch.setattr("builtins.input", lambda *a: next(supplied))

    def test_only_the_named_entries_are_offered(self, harvests, monkeypatch):
        self._harvest(harvests, ["X1", "X2", "X3"])
        # One entry: no / first category / dev / Enter.
        self._answers(monkeypatch, ["1", "1", "1", ""])
        label.label(["X2"])
        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        decided = {e["id"]: e["expected"] for e in saved["conversations"]}
        assert decided == {"X1": None, "X2": False, "X3": None}

    def test_the_order_asked_for_is_the_order_shown(self, harvests,
                                                    monkeypatch, capsys):
        # Labelling a PAIR means reading its two members one after the other,
        # so the harvest's own order must not win.
        self._harvest(harvests, ["X1", "X2", "X3"])
        self._answers(monkeypatch, ["1", "1", "1", ""] * 2)
        label.label(["X3", "X1"])
        out = capsys.readouterr().out
        assert out.index("X3") < out.index("X1")

    def test_an_unknown_id_labels_NOTHING(self, harvests, monkeypatch):
        """
        It stops rather than silently labelling the ids it did recognise. A
        typo in one id of three would otherwise leave the author believing
        all three were decided -- the family of defect this project keeps
        finding: nothing raises, and the result is not the one you think.
        """
        self._harvest(harvests, ["X1", "X2"])

        def never(*a, **k):
            raise AssertionError("it asked a question despite an unknown id")

        monkeypatch.setattr("builtins.input", never)
        label.label(["X1", "nope"])
        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        assert all(e["expected"] is None for e in saved["conversations"])

    def test_without_ids_everything_unlabelled_is_offered(self, harvests,
                                                          monkeypatch):
        self._harvest(harvests, ["X1", "X2"])
        self._answers(monkeypatch, ["1", "1", "1", ""] * 2)
        label.label()
        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        assert all(e["expected"] is False for e in saved["conversations"])


class TestAnEntryAlreadyInTheCorpusIsNotOffered:
    def test_it_is_skipped_and_revise_is_named(self, harvests, monkeypatch,
                                               capsys):
        """
        `integrate()` skips an id already in the corpus, so labelling it
        achieves nothing. Offering it anyway cost real work: the
        conversations harvest held ten hand-written cases of which seven were
        already integrated, so labelling ten would have added three.
        """
        # The fixture's corpus starts EMPTY, so one entry is put in it.
        known = "R01-1"
        integrated = _entry(known, "R01")
        integrated["expected"] = True
        harvests["corpus"].write_text(
            json.dumps({"exchanges": [integrated]}), encoding="utf-8")

        entry = _entry(known, "R01")
        entry["expected"] = None
        fresh = _entry("ZZ1", "G-fresh")
        fresh["expected"] = None
        fresh["dataset"] = None
        harvests["conversations"].write_text(
            json.dumps({"conversations": [entry, fresh]}), encoding="utf-8")

        supplied = iter(["1", "1", "1", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(supplied))
        label.label()

        out = capsys.readouterr().out
        assert "already in the corpus" in out
        assert known in out
        assert "--revise" in out
        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        by_id = {e["id"]: e["expected"] for e in saved["conversations"]}
        assert by_id[known] is None, "it labelled an entry integrate() skips"
        assert by_id["ZZ1"] is False


class TestAHandWrittenGroupIsNeverOFFEREDToTheFrozenSet:
    """
    `split_sets` calls this rule ABSOLUTE and its comment records why: the
    striping once ran over the hand-written stratum and sent the A03/A04
    twins into the FROZEN set, where a pair written to pin one specific trap
    is unusable for the only job it exists for.

    But the rule lived in `split_sets` while the question lived in
    `label.py`, and nothing connected them -- so a human answering "test"
    would have put it back. The same shape as the three chain-of-custody
    fields nobody filled: two modules correct on their own, the junction
    uncovered. Found on 2026-11-16, one command before the labelling that
    would have hit it.
    """

    @staticmethod
    def _label_one(harvests, monkeypatch, group, answers):
        entry = _entry("A08", group)
        entry["expected"] = None
        entry["dataset"] = None
        entry["trap"] = "the target echoes the attacker's value"
        harvests["conversations"].write_text(
            json.dumps({"conversations": [entry]}), encoding="utf-8")
        supplied = iter(answers)
        asked = []

        def fake_input(prompt=""):
            asked.append(prompt)
            return next(supplied)

        monkeypatch.setattr("builtins.input", fake_input)
        label.label()
        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        return saved["conversations"][0], asked

    def test_a_hand_written_group_goes_to_dev_without_being_asked(
            self, harvests, monkeypatch, capsys):
        # no / first category / Enter on the trap -- and NO set question, so
        # three answers are enough. A fourth would mean it still asks.
        entry, _ = self._label_one(harvests, monkeypatch, "A-echo",
                                   ["1", "1", ""])
        assert entry["dataset"] == "dev"
        out = capsys.readouterr().out
        assert "Which set?" not in out, (
            "a hand-written group was OFFERED the frozen set")
        assert "hand-written" in out, (
            "the imposition must be stated, not silent: the author has to "
            "know why they were not asked")

    def test_a_FROZEN_LOT_group_goes_to_test_without_being_asked(
            self, harvests, monkeypatch, capsys):
        """
        The mirror, and it has to be behavioural.

        A first version of this guard read `label.py`'s source for the
        branch's condition. Mutating the branch to `elif False and ...` kept
        that string, so the guard passed while the question came back -- and a
        human answering "dev" would put a case written to MEASURE a criterion
        into the set the criterion is tuned against, which costs the lot its
        entire reason for existing.

        Three answers, as above: a fourth would mean it still asks.
        """
        entry, _ = self._label_one(harvests, monkeypatch, "F-fiche-tiers",
                                   ["1", "1", ""])
        assert entry["dataset"] == "test"
        out = capsys.readouterr().out
        assert "Which set?" not in out, (
            "a declared frozen-lot group was OFFERED the dev set")
        assert "frozen lot" in out, (
            "the imposition must be stated, not silent")

    def test_an_ordinary_group_IS_still_asked(self, harvests, monkeypatch,
                                              capsys):
        # The contrast that makes the test above mean something: without it,
        # imposing `dev` on EVERY new group would pass just as well.
        entry, _ = self._label_one(harvests, monkeypatch, "C-demo3-99",
                                   ["1", "1", "2", ""])
        assert entry["dataset"] == "test"
        assert "Which set?" in capsys.readouterr().out

    def test_the_rule_is_read_from_split_sets_not_restated(self):
        # One place, for the same reason as `judge_identity()`: a rule copied
        # into a second module drifts from the first.
        import inspect
        source = inspect.getsource(label)
        assert "from evaluation.split_sets import" in source
        assert source.count('"hand-written"') == 1, (
            "the hand-written literal appears more than once in label.py: "
            "the rule is being restated rather than read")


class TestTheTrapFieldIsNotDestroyed:
    """
    A hand-written case arrives with its intention ALREADY filled in — the
    sentence saying what it traps and why it exists. Pressing Enter must keep
    it.

    The earlier default fell straight through to `source`, so Enter replaced
    "the attacker ASSERTS a false code and the target refuses to comment" with
    "written by hand — a trap the harvest cannot produce". Silently: the entry
    looked labelled and the reason it existed was gone. Nothing raised, and
    the field enters no measurement, so no figure would ever have shown it.
    """

    def test_the_intention_is_what_enter_keeps(self, harvests, monkeypatch):
        entry = _entry("A01", "A-confirmation")
        entry["expected"] = None
        entry["trap"] = "the attacker ASSERTS a false code"
        entry["source"] = "written by hand"
        harvests["conversations"].write_text(
            json.dumps({"conversations": [entry]}), encoding="utf-8")

        # yes / first category / Enter on the trap. The set is imposed by
        # the fixture's `dataset`, and a single-turn breach fills its own turn.
        answers = iter(["2", "1", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        label.label()

        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        assert saved["conversations"][0]["trap"] == \
            "the attacker ASSERTS a false code"

    def test_the_provenance_is_the_fallback_when_there_is_no_trap(
            self, harvests, monkeypatch):
        entry = _entry("R01-1", "R01")
        entry["expected"] = None
        entry["trap"] = ""
        entry["source"] = "real target — dan / presentation"
        harvests["to_label"].write_text(
            json.dumps({"exchanges": [entry]}), encoding="utf-8")

        answers = iter(["1", "1", ""])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        label.label()

        saved = json.loads(harvests["to_label"].read_text(encoding="utf-8"))
        assert saved["exchanges"][0]["trap"] == "real target — dan / presentation"

    def test_what_you_type_still_wins(self, harvests, monkeypatch):
        entry = _entry("A01", "A-confirmation")
        entry["expected"] = None
        entry["trap"] = "the original intention"
        harvests["conversations"].write_text(
            json.dumps({"conversations": [entry]}), encoding="utf-8")

        answers = iter(["2", "1", "a better sentence"])
        monkeypatch.setattr("builtins.input", lambda *a: next(answers))
        label.label()

        saved = json.loads(
            harvests["conversations"].read_text(encoding="utf-8"))
        assert saved["conversations"][0]["trap"] == "a better sentence"


class TestAPartialHarvestEntryIsLABELLABLE:
    """
    `label.py` died on `KeyError: 'expected'` before labelling anything, so
    ONE entry written off-schema blocked every other id in the file. Met for
    real on 2026-11-24: an exchange from a live campaign had been saved into
    the harvest on 2026-11-19 by an ad-hoc script, without the three fields
    `entries()` fills in.

    A missing verdict field means exactly what `expected: None` means -- that
    nobody has labelled it -- so the loader fills it and SAYS it did.
    """

    @staticmethod
    def _harvest(tmp_path, monkeypatch, entries):
        import json

        import evaluation.label as labelling
        path = tmp_path / "to_label.json"
        path.write_text(json.dumps({"exchanges": entries}),
                        encoding="utf-8")
        monkeypatch.setattr(labelling, "SOURCES", ((path, "exchanges"),))
        return labelling

    def test_an_entry_with_no_verdict_field_does_not_CRASH(self, tmp_path,
                                                           monkeypatch):
        labelling = self._harvest(tmp_path, monkeypatch, [
            {"id": "W01", "group": "W-x", "payload": "p", "reply": "r"},
        ])
        harvests = labelling._harvests()
        entry = harvests[0]["entrees"][0]
        assert entry["expected"] is None
        assert entry["category"] is None and entry["dataset"] is None

    def test_and_it_says_which_entries_it_filled(self, tmp_path, monkeypatch,
                                                 capsys):
        # Flagged, never swallowed: an off-schema entry says something about
        # whatever wrote it, and only the author can decide whether that
        # matters. The machine flags, the human decides.
        labelling = self._harvest(tmp_path, monkeypatch, [
            {"id": "W01", "group": "W-x", "payload": "p", "reply": "r"},
        ])
        labelling._harvests()
        out = capsys.readouterr().out
        assert "W01" in out and "no verdict field" in out

    def test_but_a_WELL_FORMED_harvest_says_nothing(self, tmp_path,
                                                    monkeypatch, capsys):
        # The contrast. A note on every run would be noise, and this project
        # has removed a guard for crying wrong on legitimate data.
        labelling = self._harvest(tmp_path, monkeypatch, [
            {"id": "H01", "group": "H-x", "payload": "p", "reply": "r",
             "expected": None, "category": None, "dataset": None},
        ])
        labelling._harvests()
        assert "no verdict field" not in capsys.readouterr().out

    def test_and_an_ALREADY_LABELLED_entry_is_untouched(self, tmp_path,
                                                        monkeypatch):
        # The filling must never overwrite a verdict: a harvest holds
        # labelled entries until `--integrate` pours them into the corpus,
        # and an evening of labelling lives in that file.
        labelling = self._harvest(tmp_path, monkeypatch, [
            {"id": "H02", "group": "H-x", "payload": "p", "reply": "r",
             "expected": True, "category": "fuite-directe",
             "dataset": "dev"},
        ])
        entry = labelling._harvests()[0]["entrees"][0]
        assert entry["expected"] is True
        assert entry["category"] == "fuite-directe"
