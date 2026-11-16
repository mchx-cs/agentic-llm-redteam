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
import pathlib
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

