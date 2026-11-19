"""
Tests for `--attempts` (2026-11-19).

The defect it fixes: the report's own no-finding block advises
`--only <technique> --no-adaptation` to obtain an INDEPENDENT bound, and the
CLI could not give more than three attempts — where the rule of three bounds
3/3 = 100%, which is the project's own starting point for phase 13 ("our 'no
findings' bounds nothing"). The one place this tool gives a numeric bound was
advised by a document and unreachable from the command line.

No LLM call: `run_campaign` is replaced, so what is checked is the WIRING —
that the number reaches the plan, the loop and the messages together.
"""

import ast
import pathlib

import pytest

import main


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    def refuse(*_, **__):
        raise AssertionError("appel à un modèle depuis tests/ : interdit.")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuse, raising=False)


class TestTheNumberREACHESTheCampaign:
    def test_the_flag_is_passed_through(self, monkeypatch, tmp_path):
        seen = {}

        def fake_campaign(*args, **kwargs):
            seen.update(kwargs)
            return {"status": "no_finding", "findings": [], "launched": [],
                    "plan": {"attempts": [], "skipped": []},
                    "observations": [], "states": [],
                    "call_log": {"calls": 0, "tokens": 0,
                                 "truncated_replies": []}}

        monkeypatch.setattr(main, "run_campaign", fake_campaign)
        main.cli(["--target", "mock", "--attempts", "30",
                  "--report", str(tmp_path)])
        assert seen.get("attempts") == 30, (
            "the flag that cannot reach run_campaign is the defect it was "
            "written to fix, one level down")

    def test_the_French_alias_works_too(self, monkeypatch, tmp_path):
        # Every option keeps its French name: a documented interface does not
        # get pulled from under its users by a translation.
        seen = {}
        monkeypatch.setattr(
            main, "run_campaign",
            lambda *a, **k: seen.update(k) or {
                "status": "no_finding", "findings": [], "launched": [],
                "plan": {"attempts": [], "skipped": []}, "observations": [],
                "states": [], "call_log": {"calls": 0, "tokens": 0,
                                           "truncated_replies": []}})
        main.cli(["--target", "mock", "--tentatives", "12",
                  "--report", str(tmp_path)])
        assert seen.get("attempts") == 12

    def test_omitting_it_leaves_the_MODULES_budget(self, monkeypatch,
                                                   tmp_path):
        # The default has to stay the module constant, not None pushed into a
        # range(): a campaign run without the flag must behave exactly as it
        # did before the flag existed.
        seen = {}
        monkeypatch.setattr(
            main, "run_campaign",
            lambda *a, **k: seen.update(k) or {
                "status": "no_finding", "findings": [], "launched": [],
                "plan": {"attempts": [], "skipped": []}, "observations": [],
                "states": [], "call_log": {"calls": 0, "tokens": 0,
                                           "truncated_replies": []}})
        main.cli(["--target", "mock", "--report", str(tmp_path)])
        assert seen.get("attempts") is None


class TestTheBudGETIsUsedEVERYWHEREOrNowhere:
    """
    A plan built for one budget and a loop running another would announce a
    coverage it never attempted — which is the lie by omission the Coverage
    section exists to prevent. So the number is read into ONE local name and
    every use reads that name.
    """

    @staticmethod
    def _body():
        source = pathlib.Path(main.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        return next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "run_campaign")

    def test_the_constant_is_read_ONCE_and_only_as_the_default(self):
        """
        Not "never": the default has to come from somewhere, and that is the
        constant. The property is that it is read EXACTLY once, in the line
        that establishes the budget — a second read is a use that ignores the
        flag.

        A first version of this test asserted the constant was gone
        altogether, and failed on the default itself. "Not read" is not the
        property; "read once, in one place" is.
        """
        body = self._body()
        reads = [node for node in ast.walk(body)
                 if isinstance(node, ast.Name) and node.id == "MAX_ATTEMPTS"]
        assert len(reads) == 1, (
            f"{len(reads)} read(s) of MAX_ATTEMPTS inside run_campaign: "
            f"every one beyond the default is a place the flag cannot reach")

        default = next(
            node for node in ast.walk(body)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "budget"
                    for target in node.targets))
        assert "MAX_ATTEMPTS" in ast.unparse(default.value)
        assert "attempts" in ast.unparse(default.value), (
            "the flag has to win over the constant, not the other way round")

    def test_the_plan_and_the_loop_get_the_SAME_number(self):
        """
        Checked on the source rather than by running a campaign, because the
        failure mode is two different numbers in two places — which a single
        campaign with the default and the constant equal would hide.
        """
        source = pathlib.Path(main.__file__).read_text(encoding="utf-8")
        assert "plan_campaign(profile, budget," in source
        assert "range(1, budget + 1)" in source
        assert "{number}/{budget}" in source


class TestWhatTheHelpPROMISES:
    def test_it_names_the_configuration_that_can_BOUND_a_zero(self):
        """
        The flag exists for one reason, and the help has to say which: at 3
        attempts the rule of three gives 100%, so a reader who does not know
        that will not think to raise it.
        """
        import contextlib
        import io

        output = io.StringIO()
        with contextlib.redirect_stdout(output), pytest.raises(SystemExit):
            main.cli(["--help"])
        help_text = output.getvalue()
        assert "--attempts" in help_text
        assert "--no-adaptation" in help_text, (
            "independence needs BOTH, and a help that names only one sends "
            "the reader to a bound that does not hold")
        assert "10%" in help_text
