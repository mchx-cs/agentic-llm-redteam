"""
tests/test_check_indirect.py — the level `check_indirect.py` actually looks at.

`check_indirect.py` is a hand-run COMMAND that calls a model, so it has no
business running here. What IS testable without one is its glue: which levels
it decides to draw. And that glue broke the day level 0 arrived — `0` is a
valid level and a falsy integer, so `if arguments.level` ran EVERY level when
the operator asked for exactly one, which is the level that exists to be
looked at on its own.

The test DRIVES `main()` rather than reading its source. That is the project's
own lesson, paid for on 2026-11-19: an argument spliced into the wrong call
went past thirteen tests because not one of them drove `main()`.
"""

import pytest

import check_indirect


@pytest.fixture
def drawn(monkeypatch):
    """Record which levels `main()` asked for, without calling a model."""
    seen = []

    def faux(level, payload, question):
        seen.append(level)
        return "ok"

    monkeypatch.setattr(check_indirect, "one_draw", faux)
    return seen


class TestWhichLevelsItDraws:

    def test_level_ZERO_draws_ONLY_level_zero(self, drawn):
        """
        The falsy-integer trap, and it is not pedantry: a command that
        silently draws four levels where one was asked spends four target
        exchanges and prints three the operator did not want.
        """
        assert check_indirect.main(["--level", "0"]) == 0
        assert drawn == [0]

    def test_a_nonzero_level_draws_only_it(self, drawn):
        # The contrast, without which the test above would pass on a command
        # that always draws exactly one level.
        check_indirect.main(["--level", "2"])
        assert drawn == [2]

    def test_no_level_draws_EVERY_level(self, drawn):
        from targets.docs import LEVELS
        check_indirect.main([])
        assert drawn == sorted(LEVELS), (
            "the default must walk the whole ladder: a command that skipped "
            "the bottom rung would show the channel on the levels that "
            "already had it")

    def test_an_unknown_level_is_REFUSED(self, drawn):
        with pytest.raises(SystemExit):
            check_indirect.main(["--level", "9"])
        assert drawn == []
