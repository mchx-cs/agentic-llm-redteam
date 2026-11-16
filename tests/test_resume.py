"""
Tests for resuming an interrupted evaluation.

A full consultation is ~301,000 tokens over several hundred sequential calls,
so a blip on call 150 of 154 loses the run. These check the three properties
that make a cache safe to use on a MEASUREMENT, which is a harsher bar than
making it work:

1. it never changes the figures — a run served from cache and a run that asks
   the judge must agree, or the cache is a second source of truth;
2. it never blends two judges, two instruction languages, or two versions of
   the same exchange;
3. it does NOT survive a finished run, because the judge is not
   deterministic and a surviving cache would turn every rerun into a replay.

No model is called: a verdict is a dict, and that is all this layer handles.
"""

import json

import pytest

from evaluation.resume import Cache, digest, path_for

JUDGE = "groq/openai/gpt-oss-120b"
VERDICT = {"reussi": True, "critere": "divulgation", "analyse": "a",
           "valeur": "X", "tour": 1, "brut": "{}"}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    import evaluation.resume
    monkeypatch.setattr(evaluation.resume, "FOLDER", tmp_path)
    return Cache("dev", JUDGE, "fr")


class TestItRemembers:
    def test_a_verdict_comes_back(self, cache):
        cache.put("D01", "Utilisateur : x", VERDICT)
        assert cache.get("D01", "Utilisateur : x") == VERDICT

    def test_an_unknown_entry_returns_None(self, cache):
        assert cache.get("D01", "Utilisateur : x") is None

    def test_it_is_FLUSHED_not_buffered(self, cache):
        """
        The whole point: an interruption must keep what already happened.
        Buffered writes would lose precisely the run the cache exists for.
        """
        cache.put("D01", "q", VERDICT)
        assert path_for and cache.path.exists()
        assert "D01" in cache.path.read_text(encoding="utf-8")

    def test_a_new_cache_reads_what_the_old_one_wrote(self, cache):
        cache.put("D01", "q", VERDICT)
        resumed = Cache("dev", JUDGE, "fr")
        assert resumed.get("D01", "q") == VERDICT


class TestWhatInvalidatesAVerdict:
    def test_a_different_JUDGE_is_not_reused(self, cache):
        """
        Resuming across a change of judge would blend two models in one
        figure — the blending the project refuses for defence levels, for
        formats and for languages alike.
        """
        cache.put("D01", "q", VERDICT)
        assert Cache("dev", "other/model", "fr").get("D01", "q") is None

    def test_a_different_LANGUAGE_is_not_reused(self, cache):
        # `--language fr` and `--language en` are the two arms of a
        # comparison; mixing them would destroy it.
        cache.put("D01", "q", VERDICT)
        assert Cache("dev", JUDGE, "en").get("D01", "q") is None

    def test_a_CHANGED_QUESTION_is_not_reused(self, cache):
        # A verdict is about the text the judge was sent. If the exchange
        # changed, the cached verdict is about something else — and the id
        # alone would not have caught it.
        cache.put("D01", "Utilisateur : x", VERDICT)
        assert cache.get("D01", "Utilisateur : y") is None

    def test_a_different_SET_has_its_own_cache(self, cache):
        cache.put("D01", "q", VERDICT)
        assert Cache("test", JUDGE, "fr").get("D01", "q") is None

    def test_a_half_written_last_line_is_skipped(self, cache):
        """
        Exactly what an interruption leaves behind, and the reason the format
        is JSONL: one broken line costs one verdict, not the whole run.
        """
        cache.put("D01", "q", VERDICT)
        with cache.path.open("a", encoding="utf-8") as f:
            f.write('{"id": "D02", "dig')
        resumed = Cache("dev", JUDGE, "fr")
        assert resumed.get("D01", "q") == VERDICT
        assert len(resumed) == 1


class TestItDoesNotSurviveAFinishedRun:
    """
    The decision that shapes the whole module. The judge is not
    deterministic — measured on this project, E10-b gave
    [True, True, True, True, False] at temperature 0 with `seed` changing
    nothing. A cache that outlived a completed run would make every rerun
    reproduce the first instead of resampling, and the variance the project
    measured would quietly vanish from every figure after it.
    """

    def test_discard_removes_it(self, cache):
        cache.put("D01", "q", VERDICT)
        assert cache.path.exists()
        cache.discard()
        assert not cache.path.exists()

    def test_discard_is_safe_when_there_is_nothing(self, cache):
        cache.discard()          # must not raise
        cache.discard()

    def test_the_evaluation_discards_on_a_normal_finish(self):
        # Checked in the source rather than by running: running it needs a
        # model. What matters is that the call is there and unconditional.
        import inspect

        from evaluation import evaluate_judge
        source = inspect.getsource(evaluate_judge.evaluate)
        assert "cache.discard()" in source
        after_discard = source.split("cache.discard()")[1]
        assert "return counts, metrics" in after_discard, (
            "discard() must be on the path that finishes, not in a branch")


class TestTheFiguresDoNotMove:
    def test_a_cached_run_and_a_fresh_run_agree(self, tmp_path, monkeypatch):
        """
        The property that makes a cache acceptable on a MEASUREMENT: it must
        be invisible in the result. If a resumed run could differ from an
        uninterrupted one, the cache would be a second source of truth.
        """
        import evaluation.evaluate_judge as evaluator
        import evaluation.resume
        monkeypatch.setattr(evaluation.resume, "FOLDER", tmp_path)

        exchanges = [
            {"id": "A", "expected": True, "payload": "p1", "reply": "r1",
             "group": "A", "dataset": "dev", "category": "fuite-directe",
             "trap": "", "languages": "fr->fr", "labelled_by": "author"},
            {"id": "B", "expected": False, "payload": "p2", "reply": "r2",
             "group": "B", "dataset": "dev", "category": "controle",
             "trap": "", "languages": "fr->fr", "labelled_by": "author"},
        ]
        monkeypatch.setattr(evaluator, "load_exchanges", lambda d: exchanges)

        verdicts = {"p1": {"reussi": True, "critere": "divulgation",
                           "analyse": "", "valeur": None, "tour": None},
                    "p2": {"reussi": False, "critere": "aucun",
                           "analyse": "", "valeur": None, "tour": None}}
        calls = []

        def fake(exchange, language):
            calls.append(exchange["id"])
            return verdicts[exchange["payload"]]

        monkeypatch.setattr(evaluator, "ask_the_judge", fake)

        first_counts, first_metrics = evaluator.evaluate("dev")
        assert calls == ["A", "B"]

        # Now simulate an interruption after the first entry: put A back in a
        # cache and run again.
        cache = evaluation.resume.Cache(
            "dev", f"{evaluator.JUDGE_PROFILE}/"
                   f"{evaluator.PROFILES[evaluator.JUDGE_PROFILE]['model']}",
            "fr")
        cache.put("A", evaluator.question_asked(exchanges[0]), verdicts["p1"])
        calls.clear()

        second_counts, second_metrics = evaluator.evaluate("dev")
        assert calls == ["B"], "A should have come from the cache"
        assert second_counts == first_counts
        assert second_metrics == first_metrics


class TestTheDigest:
    def test_the_same_text_gives_the_same_digest(self):
        assert digest("abc") == digest("abc")

    def test_different_text_gives_a_different_digest(self):
        assert digest("abc") != digest("abd")

    def test_it_is_built_from_the_REAL_question(self):
        """
        The digest must come from the same functions that build the question
        for the judge. A digest over a reconstruction would let a stale
        verdict through, which is the one thing this must not do.
        """
        import inspect

        from evaluation import evaluate_judge
        source = inspect.getsource(evaluate_judge.question_asked)
        assert "build_conversation_question" in source
        assert "build_question" in source


class TestTheCacheIsGitignored:
    def test_it_will_never_be_committed(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        ignored = (root / ".gitignore").read_text(encoding="utf-8")
        assert "evaluation/.verdicts-" in ignored, (
            "a run's verdicts are a working file; committing them would put "
            "a model's output where the corpus lives")
