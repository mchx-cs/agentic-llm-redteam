"""
Les chiffres du README que la machine peut vérifier elle-même.

POURQUOI CE FICHIER EXISTE, et c'est un compte précis : le nombre de tests
annoncé dans le README a été corrigé à la main cinq fois — 909, 1 002, 1 293,
1 378, 1 392 — dont QUATRE dans la seule session du 2026-11-20, et deux fois
parce que mon propre travail venait de le périmer entre deux commits.

Le projet enregistre la leçon depuis le 2026-11-12 : « a contradiction between
code and documentation raises nothing and breaks no test. It is only found by
rereading with the code in front of you. » Ce fichier en fait une exception :
celle-là se trouve toute seule.

Le coût est assumé et il est le vrai prix d'une affirmation chiffrée dans une
vitrine : ajouter un test demande désormais de corriger une ligne du README.
C'est la même discipline que `check_excerpt.py`, qui impose de régénérer un
extrait plutôt que de le retoucher.

Ce qui n'est PAS ici : les chiffres qui demandent une mesure (les figures du
juge, les taux, les intervalles). Ceux-là ne se vérifient pas sans modèle ni
sans quota, et un test qui les devinerait serait pire qu'absent.
"""

import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def collected():
    """
    Combien de tests pytest collecte réellement.

    Un sous-processus, et `--collect-only`, donc rien ne s'exécute : ce test
    ne relance pas la suite, il la compte. Une collecte illisible ÉCHOUE au
    lieu d'être sautée — un garde qui se saute lui-même est exactement ce que
    ce fichier existe pour empêcher.
    """
    out = subprocess.run(
        # Sans `-q` : c'est `-q` qui SUPPRIME la ligne « N tests collected »,
        # et le fixture a d'abord echoue pour cette raison -- bruyamment, ce
        # qui est la propriete voulue.
        [sys.executable, "-m", "pytest", str(ROOT / "tests"),
         "--collect-only", "-p", "no:cacheprovider"],
        capture_output=True, text=True, timeout=600, cwd=ROOT)
    found = re.search(r"(\d+) tests? collected", out.stdout)
    assert found, (
        "la collecte n'a rien dit de lisible :\n"
        + (out.stdout or out.stderr)[-800:])
    return int(found.group(1))


def _readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_test_COUNT_is_the_real_one(collected):
    """
    Le chiffre annoncé est le chiffre collecté.

    Il est dans la première moitié du README, dans la phrase qui fonde la
    promesse « `tests/` never calls a model » — donc un lecteur le prend pour
    la taille de la garantie. Un chiffre périmé y est une affirmation fausse
    sur la seule chose qu'un visiteur ne peut pas vérifier sans cloner.
    """
    found = re.search(r"([\d,]+) pytest tests", _readme())
    assert found, "le README n'annonce plus de nombre de tests"
    announced = int(found.group(1).replace(",", ""))
    assert announced == collected, (
        f"le README annonce {announced} tests, pytest en collecte "
        f"{collected}. Corriger le README, pas ce test : c'est la cinquième "
        f"fois que ce chiffre se périme, et la raison de ce fichier.")


def test_the_figure_is_WRITTEN_the_way_the_readme_writes_figures():
    # Un détail, mais il décide si le garde ci-dessus sait lire : le README
    # écrit ses milliers avec une virgule, et un passage à l'espace insécable
    # ou au point rendrait l'expression muette — donc le garde passerait en
    # ne comparant rien, ce qui est la tautologie que ce projet a rencontrée
    # cinq fois dans ses propres gardes.
    assert re.search(r"\d,\d{3} pytest tests", _readme()), (
        "le nombre de tests doit rester écrit `1,405` : c'est ce que "
        "l'expression du garde reconnaît")


def test_and_the_promise_beside_it_is_still_there(collected):
    """
    Le chiffre ne vaut que par la phrase qu'il quantifie.

    « tests/ never calls a model » est une promesse tenue par un fixture dans
    `tests/test_collect_conversations.py` et par la discipline du projet
    ailleurs. Si elle disparaissait du README, le chiffre resterait vrai et
    ne dirait plus rien.
    """
    assert "never calls a model" in _readme()
