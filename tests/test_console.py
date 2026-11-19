"""
Tests for the output encoding (2026-11-19).

The defect: Windows gives a REDIRECTED stdout the locale codec (cp1252), so
`python main.py --target … > campaign.log` dies from inside `print` on the
first character outside it. Measured on this repository's own library:
**13 techniques out of 58 carry a payload cp1252 cannot encode** — braille,
zalgo, base2048, Chinese, emoji, raw ANSI — so a campaign that sends one of
them loses the run after the attempt has been sent and the throughput spent.

Not hypothetical, and not only a measurement problem: it killed a run on
2026-11-19, and the exposure is in the tool.
"""

import ast
import pathlib

import pytest

from console import write_in_utf8

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Its own venv, and it imports NOTHING from this project: that is what keeps
# garak's 164 dependencies outside. Importing `console` there to fix a
# redirection would trade the isolation for the convenience.
EXEMPT = "payloads/garak_export.py"


def _entry_points():
    """Every file in the repository that runs as a program."""
    found = {}
    for path in sorted(list(ROOT.glob("*.py"))
                       + list(ROOT.glob("evaluation/*.py"))
                       + list(ROOT.glob("payloads/*.py"))
                       + list(ROOT.glob("agents/*.py"))
                       + list(ROOT.glob("targets/*.py"))):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if (isinstance(node, ast.If)
                    and ast.unparse(node.test).startswith("__name__ ==")):
                found[str(path.relative_to(ROOT)).replace("\\", "/")] = node
    return found


class TestWhatItDoes:
    class _Stream:
        def __init__(self):
            self.asked = None

        def reconfigure(self, **kwargs):
            self.asked = kwargs

    def test_it_asks_for_utf8(self, monkeypatch):
        out, err = self._Stream(), self._Stream()
        monkeypatch.setattr("sys.stdout", out)
        monkeypatch.setattr("sys.stderr", err)
        write_in_utf8()
        assert out.asked == {"encoding": "utf-8", "errors": "replace"}
        assert err.asked == {"encoding": "utf-8", "errors": "replace"}, (
            "stderr too: a traceback carrying a target's reply would die on "
            "the way out, which is the one moment you need to read it")

    def test_it_is_INERT_where_it_cannot_apply(self, monkeypatch):
        """
        `pytest` replaces stdout with a capture object, and so does any caller
        that pipes us. Neither has `reconfigure`, and neither is a reason to
        refuse to run.
        """
        monkeypatch.setattr("sys.stdout", object())
        monkeypatch.setattr("sys.stderr", object())
        write_in_utf8()      # must not raise

    def test_a_stream_that_REFUSES_does_not_stop_the_work(self, monkeypatch):
        """
        A detached or closed stream raises on `reconfigure`. Failing here
        would be the defect inverted: the guard exists to let the work
        proceed, so the guard failing must never be what stops it.
        """
        class Refuses:
            def reconfigure(self, **_):
                raise ValueError("detached")

        monkeypatch.setattr("sys.stdout", Refuses())
        monkeypatch.setattr("sys.stderr", Refuses())
        write_in_utf8()      # must not raise


class TestEVERYEntryPointCallsIt:
    """
    The sweep, rather than a list somebody has to remember to extend.

    This project has twice added a lot of hand-written cases that the set
    split did not know about, and has fixed this same encoding exposure in
    ONE module while noting that the others had it. A rule derived from the
    repository fails the day a new entry point appears — which is exactly when
    the decision has to be made deliberately rather than inherited.
    """

    def test_there_are_entry_points_to_check(self):
        # Without this the sweep below would pass on an empty set, which is
        # the tautology this project has met four times.
        assert len(_entry_points()) > 15

    @pytest.mark.parametrize("name", sorted(_entry_points()))
    def test_the_first_thing_it_does_is_make_its_output_utf8(self, name):
        if name == EXEMPT:
            pytest.skip(f"{name} imports nothing from this project")
        first = _entry_points()[name].body[0]
        assert ast.unparse(first) == "write_in_utf8()", (
            f"{name} runs as a program, so its output can be redirected to a "
            f"file, and 13 of the library's 58 techniques carry a payload "
            f"cp1252 cannot encode. The call goes FIRST, before anything "
            f"prints.")

    def test_the_EXEMPTION_is_a_decision_and_not_an_oversight(self):
        """
        `garak_export` is exempt BECAUSE it imports nothing from this project.
        If that ever stops being true the exemption has lost its reason, and
        this says so instead of leaving a silent hole.
        """
        tree = ast.parse((ROOT / EXEMPT).read_text(encoding="utf-8"))
        imported = {
            node.module.split(".")[0] if isinstance(node, ast.ImportFrom)
            else name.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for name in (node.names if isinstance(node, ast.Import)
                         else [node])
        }
        ours = {"console", "config", "llm_client", "report", "stats", "audit",
                "main", "agents", "targets", "payloads", "evaluation"}
        assert not (imported & ours), (
            f"{EXEMPT} now imports {imported & ours} from this project: it "
            f"runs in garak's venv, so either that import is a mistake or the "
            f"exemption no longer has a reason and the module must call "
            f"write_in_utf8() like the others")


class TestItIsNOTCalledOnImport:
    """
    Reconfiguring a stream is global: a module doing it at import time changes
    the interpreter underneath whoever imported it, `pytest` included. The
    same reason the budget is armed by the orchestrator and not by
    `llm_client` — a measurement script must not be cut off because importing
    something rearranged its output.
    """

    @pytest.mark.parametrize("name", sorted(_entry_points()))
    def test_the_call_is_inside_the_entry_block(self, name):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        at_module_level = [
            node for node in tree.body
            if isinstance(node, ast.Expr)
            and ast.unparse(node).startswith("write_in_utf8(")]
        assert not at_module_level, (
            f"{name} calls it at import time, which reconfigures stdout for "
            f"anything that imports it")
