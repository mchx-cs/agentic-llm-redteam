"""
Every command-line flag must match the attribute the code reads from it.

This guards a defect class, not a single bug. Renaming identifiers while
leaving the argparse option strings alone produces code that argparse accepts
and that fails — or, worse, silently does nothing:

- `main.py` read `arguments.seulement` after `--seulement` became `--only`:
  `--only` and `--excluding` were accepted and SILENTLY IGNORED, because the
  stale attribute was only ever read on a path that was never taken;
- `collect_conversations.py` read `arguments.compare` against `--comparer`,
  `measure_multiturn.py` read `arguments.pairs` against `--paires`, and
  `handwritten_conversations.py` read `arguments.pour_in` against `--verser`.
  All three died with AttributeError the moment they were run.

None of it broke a test, because no test ran those entry points. So the check
is STATIC: it reads each module's own source, works out what dests its parser
defines, and compares that with the attributes the module reads. Nothing is
imported and nothing is executed, so it cannot call a model.
"""

import ast
import fnmatch
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# argparse puts these on the namespace by itself.
BUILT_IN = {"help"}

def _namespace_names(tree):
    """
    The variables that hold a parsed namespace, taken from the code itself.

    A fixed list of likely names ("arguments", "args"…) was the first version,
    and the check's own self-test caught it: a module that called it anything
    else would be waved through. The name is read off `… = parser.parse_args()`
    instead, so there is nothing to keep in step.
    """
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if (isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr in ("parse_args", "parse_known_args")):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            for target in targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
                elif isinstance(target, ast.Tuple):
                    found.update(e.id for e in target.elts
                                 if isinstance(e, ast.Name))
    return found


def modules_with_a_parser():
    """Every tracked module that builds an ArgumentParser."""
    listed = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT,
                            capture_output=True, text=True,
                            check=True).stdout.split()
    found = []
    for name in listed:
        if name.startswith("tests/"):
            continue
        if "ArgumentParser" in (ROOT / name).read_text(encoding="utf-8"):
            found.append(name)
    return sorted(found)


def _dest_of(call):
    """The namespace attribute one `add_argument(...)` call will set."""
    for keyword in call.keywords:
        if keyword.arg == "dest" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value
    # Otherwise argparse takes the FIRST long option, or the only short one,
    # and turns dashes into underscores.
    flags = [a.value for a in call.args
             if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    longs = [f for f in flags if f.startswith("--")]
    if longs:
        return longs[0][2:].replace("-", "_")
    if flags:
        return flags[0].lstrip("-").replace("-", "_")
    return None


def _declared_and_read(source):
    tree = ast.parse(source)
    namespaces = _namespace_names(tree)
    declared, read = set(BUILT_IN), set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)):
            if node.func.attr == "add_argument":
                dest = _dest_of(node)
                if dest:
                    declared.add(dest)
            elif node.func.attr == "set_defaults":
                declared.update(k.arg for k in node.keywords if k.arg)
        elif (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in namespaces):
            read.add(node.attr)
    return declared, read


@pytest.mark.parametrize("module", modules_with_a_parser())
def test_every_attribute_read_is_a_flag_that_exists(module):
    source = (ROOT / module).read_text(encoding="utf-8")
    declared, read = _declared_and_read(source)
    orphans = sorted(read - declared)
    assert not orphans, (
        f"{module} reads {orphans} from its parsed arguments, but its parser "
        f"defines {sorted(declared)}. A renamed identifier left an option "
        f"string behind.")


class TestTheCheckItself:
    """A check that passes on anything is worth nothing."""

    def test_it_catches_a_stale_attribute(self):
        source = (
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--only')\n"
            "a = p.parse_args()\n"
            "print(a.seulement)\n")
        declared, read = _declared_and_read(source)
        assert "seulement" in read - declared

    def test_an_explicit_dest_counts_as_declared(self):
        source = (
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--target', '--cible', dest='target')\n"
            "a = p.parse_args()\n"
            "print(a.target)\n")
        declared, read = _declared_and_read(source)
        assert not read - declared

    def test_a_french_alias_does_not_become_the_dest(self):
        # `--report`, `--rapport` sets `report`: argparse takes the FIRST long
        # option. Getting this backwards would make the check accept the very
        # mistake it exists to catch.
        source = (
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            "p.add_argument('--report', '--rapport')\n")
        declared, _ = _declared_and_read(source)
        assert "report" in declared and "rapport" not in declared

    def test_it_looks_at_more_than_one_module(self):
        # If the discovery ever returned nothing, every parametrized case
        # would vanish and the file would pass by being empty.
        assert len(modules_with_a_parser()) >= 5


class TestNoTestReadsTheAmbientJudge:
    """
    A test must not let the configured judge decide what output it expects.

    This cost a red CI: `test_the_two_formats_are_never_POOLED` asserted the
    "comparable with 89 / 100 / 96" note unconditionally. That note is
    withdrawn on any judge other than the one the figures were measured on —
    so it passed here, where `.env` sets the judge to groq, and failed in
    continuous integration, which has no `.env` and therefore the local judge.
    Green locally, red remotely, and the TEST was the thing that was wrong.

    The check is static: a test file may name `JUDGE_PROFILE` only if it also
    monkeypatches it. Reading it to build a fixture is fine; reading it to
    decide an assertion is what breaks.

    WHAT IT DOES NOT REACH, said rather than left to be discovered -- it was
    discovered, on 2026-11-23, by a test of mine that failed in CI and not
    here. The check looks for the NAME `JUDGE_PROFILE`; the same defect wears
    a second shape, a hardcoded judge IDENTITY (`"local/llama3.2"`) supplied
    as the "other" judge, which happens to BE the ambient one wherever `.env`
    is absent. Nothing is named, so nothing is flagged.

    No static rule was added for it, deliberately: three test files carry such
    a literal legitimately -- one pins `MEASURED_ON`, one supplies telemetry
    as data, one keys a cache with the SAME identity on both sides -- so the
    rule would cry wrong three times in four, and this project has removed a
    guard for crying wrong twice in four. The answer is structural instead:
    derive the other judge from `judge_identity()`, so the test is right
    under any configuration. And the reproduction that catches the whole
    class costs two commands: run the suite with `.env` moved aside, then
    with the garak snapshot moved aside too.
    """

    def test_a_test_naming_the_judge_profile_also_pins_it(self):
        import subprocess

        listed = subprocess.run(["git", "ls-files", "tests/*.py"], cwd=ROOT,
                                capture_output=True, text=True,
                                check=True).stdout.split()
        offenders = []
        for name in listed:
            source = (ROOT / name).read_text(encoding="utf-8")
            if "JUDGE_PROFILE" not in source:
                continue
            if '"JUDGE_PROFILE"' not in source:
                # Named but never passed to monkeypatch.setattr as a string.
                offenders.append(name)
        assert not offenders, (
            f"{offenders} read JUDGE_PROFILE without pinning it: the ambient "
            f"configuration will decide what the test expects, so it passes "
            f"where `.env` exists and fails in CI.")

    def test_the_check_would_catch_an_unpinned_read(self):
        # The check is a string search, so prove it discriminates.
        pinned = 'monkeypatch.setattr(m, "JUDGE_PROFILE", "x")'
        unpinned = "if JUDGE_PROFILE == 'groq': assert ..."
        assert '"JUDGE_PROFILE"' in pinned
        assert '"JUDGE_PROFILE"' not in unpinned


class TestWhatGetsSHIPPED:
    """
    A top-level module imported by the code must be in `py-modules`.

    THE DEFECT, found on 2026-11-20 while wiring the transports: `console.py`
    arrived on 2026-11-19, 21 files import it, `main` among them -- and it was
    not in `pyproject.toml`'s module list. So `pip install .` produced a
    `redteam` command that died at import, and phase 10's whole deliverable
    is that packaged command.

    Nothing in the repository could see it, because the tests run from the
    CHECKOUT, where the file is simply there. Same shape as the gitignored
    garak snapshot that turned CI red for six days: **an environment richer
    than the one the artefact runs in.**

    Static, like the rest of this file: nothing is imported, nothing runs.
    """

    #: Packages are found by `packages.find`, so only top-level MODULES need
    #: listing. These are not modules of ours.
    STANDARD_LIBRARY_AND_FRIENDS = {"openai", "pytest", "pyrit", "garak"}

    @staticmethod
    def _shipped():
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        inside = re.search(r"py-modules\s*=\s*\[(.*?)\]", text, re.S)
        assert inside, "pyproject.toml no longer declares py-modules"
        return set(re.findall(r'"([^"]+)"', inside.group(1)))

    @staticmethod
    def _top_level_modules():
        return {path.stem for path in ROOT.glob("*.py")}

    @classmethod
    def _imported_by_anyone(cls):
        """
        Top-level modules of ours that some other SHIPPED file imports.

        `tests/` is skipped, and that boundary is the rule rather than a
        convenience: the package ships what the RUNTIME needs, and tests are
        not shipped. Its first version counted them, and flagged
        `check_excerpt` -- a hand-run helper imported by nothing but its own
        test. A guard that cries wrong on legitimate files teaches people to
        ignore it, which this project has removed a guard for once already.
        """
        ours = cls._top_level_modules()
        found = {}
        for path in ROOT.rglob("*.py"):
            if any(part.startswith(".venv") for part in path.parts):
                continue
            if "tests" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:                            # pragma: no cover
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or "").split(".")[0]]
                elif isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                for name in names:
                    if name in ours and name != path.stem:
                        found.setdefault(name, path.relative_to(ROOT))
        return found

    def test_every_module_the_code_imports_is_shipped(self):
        shipped = self._shipped()
        missing = {name: by for name, by
                   in self._imported_by_anyone().items()
                   if name not in shipped}
        assert not missing, (
            "these top-level modules are imported but not shipped, so an "
            "installed `redteam` dies at import: "
            + ", ".join(f"{name} (imported by {by})"
                        for name, by in sorted(missing.items())))

    def test_and_the_guard_would_have_caught_console(self):
        """
        Not a second copy of the test above: it checks the guard's INPUT is
        what it is supposed to be. If `console` ever stopped being seen as
        imported, the test above would pass while shipping nothing -- the
        tautology this project keeps finding in its own guards.
        """
        assert "console" in self._imported_by_anyone(), (
            "console is imported by main and 20 others; a guard that cannot "
            "see that is not guarding")

    def test_a_module_NOBODY_imports_need_not_be_shipped(self):
        """
        The rule has to have a boundary, or it becomes a list to maintain.
        `check_excerpt.py` and `check_rename_damage.py` are run by hand and
        imported by nothing, so they are not part of the installed package --
        and a guard that demanded them would cry wrong on legitimate files,
        which this project has removed a guard for once already.
        """
        imported = self._imported_by_anyone()
        standalone = [name for name in ("check_excerpt",
                                        "check_rename_damage")
                      if name in self._top_level_modules()]
        assert standalone, "neither helper exists any more"
        for name in standalone:
            assert name not in imported, (
                f"{name} is run by hand and imported by no shipped file, so "
                f"it is not part of the installed package")
        # And the boundary is load-bearing rather than cosmetic: a TEST does
        # import `check_excerpt`, which is what made the rule's first
        # version demand it be shipped.
        assert (ROOT / "tests" / "test_check_excerpt.py").exists()

class TestNoMeasurementFileCanBeCOMMITTED:
    """
    Every output file a protocol DOCUMENTS must be gitignored, and its `.log`
    sibling with it.

    THE DEFECT, twice. The delivery run of 2026-11-25 put 560 KB of campaign
    stdout into the repository — every complete payload and every verbatim
    reply, which is exactly what `--abridge` exists to keep out of a public
    repository. `modes*.json` and `delivery*.json` were ignored; the `.log`
    half was not, and it had to be untracked afterwards. Then the attribution
    protocol arrived and `attribution*` matched NEITHER, so two more lines
    went in BY HAND — which is the defect, not the fix.

    So this is a SWEEP and not a list: the names are read from the run
    commands the modules document, so it fails the day a fifth protocol adds
    one. That is precisely when the decision has to be taken deliberately
    instead of inherited — the same shape as the entry-point sweep and the
    `py-modules` sweep above.

    The `.log` sibling is an INFERENCE, and declared as one: the log's name
    comes from a shell redirect that no docstring shows, so the guard assumes
    the project's convention of `<stem>.log`. Its cost if wrong is one
    unnecessary pattern; its benefit is the half that was actually forgotten.

    Static, like the rest of this file: nothing is imported, nothing runs, and
    it does not look at what happens to be on this disk — a guard that
    depended on the operator's leftovers would pass on a clean checkout.
    """

    @staticmethod
    def _documented_outputs():
        """The `--output` filenames the measurement modules document."""
        found = {}
        for path in sorted(ROOT.glob("evaluation/*.py")) + [ROOT / "main.py"]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            doc = ast.get_docstring(tree) or ""
            for name in re.findall(r"--output\s+(\S+)", doc):
                found.setdefault(name, path.relative_to(ROOT))
        return found

    @staticmethod
    def _ignored(name):
        """
        Does `.gitignore` match `name`?

        Only basename patterns are considered. Every pattern that matters
        here is one, and pretending to implement gitignore's path semantics
        would be a guard whose own correctness nobody checks.
        """
        patterns = [line.strip() for line
                    in (ROOT / ".gitignore").read_text(
                        encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")
                    and "/" not in line.strip()]
        return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)

    @staticmethod
    def _declared_prefixes():
        """
        The output-file prefix each COMPARISON declares.

        Read from the code, so a fifth comparison brings its own line here
        the day it is added. The first version of this guard swept the
        DOCSTRING's run commands instead, and a mutation showed the hole:
        removing `delivery*.log` failed nothing, because the three delivery
        runs' filenames were typed on the command line and never documented
        — so the very files whose log had to be untracked were outside its
        reach.
        """
        import evaluation.measure_modes as modes
        return {name: spec["output_prefix"]
                for name, spec in modes.ARMS.items()
                if "output_prefix" in spec}

    def test_EVERY_comparison_declares_its_output_prefix(self):
        # Without this, the test below would pass on a module where a
        # comparison had simply dropped the field.
        import evaluation.measure_modes as modes
        declared = self._declared_prefixes()
        assert set(declared) == set(modes.ARMS), (
            "these comparisons declare no output prefix, so nothing requires "
            "their files to be gitignored: "
            + ", ".join(sorted(set(modes.ARMS) - set(declared))))

    def test_every_declared_prefix_is_IGNORED_json_and_LOG(self):
        missing = []
        for arms, prefix in sorted(self._declared_prefixes().items()):
            for suffix in (".json", ".log"):
                probe = f"{prefix}-whatever{suffix}"
                if not self._ignored(probe):
                    missing.append(f"{prefix}*{suffix} (for `{arms}`)")
        assert not missing, (
            "a run writes its pairs and its stdout under these names, and "
            "the stdout carries every complete payload and every verbatim "
            "reply: " + ", ".join(missing))

    def test_the_sweep_FINDS_the_documented_outputs(self):
        # Without this, the two tests below would pass on a sweep that found
        # nothing at all -- the tautology this project has met seven times.
        found = self._documented_outputs()
        assert found, "the sweep found no documented --output at all"
        assert any(name.startswith("attribution") for name in found), found

    def test_every_documented_output_is_IGNORED(self):
        missing = {name: by for name, by
                   in self._documented_outputs().items()
                   if not self._ignored(name)}
        assert not missing, (
            "these measurement files are documented and committable, and a "
            "run writes its pairs into them: "
            + ", ".join(f"{name} (documented in {by})"
                        for name, by in sorted(missing.items())))

    def test_and_so_is_its_LOG(self):
        # The half that was forgotten, and the one that carries the payloads
        # and the target's verbatim replies.
        missing = []
        for name, by in sorted(self._documented_outputs().items()):
            log = re.sub(r"\.json$", ".log", name)
            if log != name and not self._ignored(log):
                missing.append(f"{log} (for {name}, documented in {by})")
        assert not missing, (
            "a campaign's stdout carries every complete payload and every "
            "verbatim reply: " + ", ".join(missing))

    def test_the_matcher_does_not_simply_say_YES(self):
        # The contrast, without which the two tests above would pass on an
        # `_ignored` that returned True for everything.
        assert not self._ignored("README.md")
        assert self._ignored("attribution.json")
