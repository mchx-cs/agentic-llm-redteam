# -*- coding: utf-8 -*-
"""
Les deux cartes du depot nomment CHAQUE module livre.

POURQUOI UN BALAYAGE ET NON UNE LISTE, et c'est cinq fois plutot qu'une
hypothese. Un module ecrit et absent de la carte du depot est une piece de la
vitrine qu'un lecteur ne peut pas trouver, et ce defaut s'est produit a chaque
fois qu'une piece neuve est arrivee :

- 2026-11-12 : `stats.py`, le module de la phase 13 ;
- 2026-11-17 : tout le paquet `pyrit_bridge/`, quatre fichiers ;
- 2026-11-19 : `console.py` et `targets/records.py` ;
- 2026-11-27 : HUIT fichiers, les memes dans les deux documents -- trois
  cibles (`bench`, `foreign`, `wrapping`) et cinq modules de mesure.

Chaque fois trouve par la meme lecture -- DIFFER LA CARTE CONTRE LE DISQUE --
et jamais par un test ni par une relecture du code. C'est donc la lecture
qu'une machine doit faire, comme le balayage des points d'entree et celui de
`py-modules` : une liste que quelqu'un doit penser a etendre EST le defaut, et
non le correctif.

ET IL COUVRE LES FICHIERS PAS ENCORE SUIVIS. Le 2026-11-26, un balayage qui
listait par `git ls-files` seul n'a vu un contrevenant qu'au run SUIVANT son
commit -- donc le defaut qu'il existe pour attraper partait dans le commit
meme qui l'introduisait. `--others --exclude-standard` ferme ca sans liste
d'exclusions a tenir : `.venv` et `.venv-pyrit` restent dehors parce que
`.gitignore` les cache.
"""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Les bornes de chaque bloc de carte. Un bloc dont les bornes ne
#: correspondent plus fait ECHOUER le garde au lieu de comparer un texte vide
#: -- la tautologie rencontree cinq fois dans les gardes de ce projet.
MAPS = {
    "README.md": ("├── config.py", "\n```"),
    "CLAUDE.md": ("config.py          #", "\n```"),
}

#: Exempte, avec sa raison : un marqueur de paquet n'est pas une piece a
#: trouver, et aucune des deux cartes ne liste `targets/__init__.py` ni
#: `agents/__init__.py`. Compter un marqueur ferait crier le garde faux, et ce
#: projet a supprime un garde entier pour l'avoir fait deux fois sur quatre.
NOT_A_PIECE = "__init__.py"


def _shipped_modules():
    """
    Les modules que le depot livre, SUIVIS OU PAS.

    `tests/` est dehors : les deux cartes le mentionnent comme un repertoire
    et n'en listent pas les fichiers, ce qui est un choix de presentation et
    non un oubli -- un lecteur cherche un module, pas un test.
    """
    listed = []
    for arguments in (["git", "ls-files"],
                      ["git", "ls-files", "--others", "--exclude-standard"]):
        done = subprocess.run(arguments, cwd=ROOT, capture_output=True,
                              text=True, check=True)
        listed += done.stdout.split()
    return {path for path in listed
            if path.endswith(".py")
            and not path.startswith("tests/")
            and pathlib.Path(path).name != NOT_A_PIECE}


def _names_in_the_map(document):
    start, end = MAPS[document]
    text = (ROOT / document).read_text(encoding="utf-8")
    assert text.count(start) == 1, (
        f"la carte de {document} ne commence plus par {start!r} : ce garde "
        f"comparerait un bloc qu'il n'a pas trouve. Corriger la borne, pas "
        f"le supprimer.")
    begin = text.index(start)
    stop = text.index(end, begin)
    block = text[begin:stop]
    assert len(block.splitlines()) > 20, (
        f"le bloc de carte de {document} fait {len(block.splitlines())} "
        f"lignes : les bornes ont glisse et le garde ne compare presque rien")
    return set(re.findall(r"\b([a-z_][a-z0-9_]*\.py)\b", block))


@pytest.mark.parametrize("document", sorted(MAPS))
def test_the_map_names_every_shipped_module(document):
    named = _names_in_the_map(document)
    missing = sorted(path for path in _shipped_modules()
                     if pathlib.Path(path).name not in named)
    assert not missing, (
        f"{len(missing)} module(s) livre(s) et absent(s) de la carte de "
        f"{document} : {missing}. Un lecteur du depot ne peut pas les "
        f"trouver, et c'est la cinquieme fois que ce defaut se produit. "
        f"Ajouter la ligne a la carte, avec une description tiree du "
        f"DOCSTRING du module et non devinee.")


def test_and_the_two_maps_name_the_SAME_modules():
    """
    L'autre moitie, et elle n'est pas couverte par la precedente : les deux
    cartes pourraient etre completes et decrire deux depots differents.

    Le 2026-11-27 les HUIT memes fichiers manquaient des deux cotes, ce qui
    dit que les deux cartes derivent l'une de l'autre en pratique. Si elles
    divergent, c'est qu'une piece a ete ajoutee d'un seul cote -- la forme du
    defaut des deux roadmaps, qui ont deja diverge le 2026-11-17.
    """
    readme = _names_in_the_map("README.md")
    claude = _names_in_the_map("CLAUDE.md")
    shipped = {pathlib.Path(path).name for path in _shipped_modules()}

    # Restreint aux modules LIVRES : chaque document nomme aussi des fichiers
    # qui ne sont pas a nous -- `api.py` et `routes.py` sont ceux de PyRIT,
    # cites en prose -- et exiger l'egalite brute ferait crier le garde faux.
    assert (readme & shipped) == (claude & shipped), (
        "les deux cartes ne decrivent pas le meme depot : "
        f"README seul {sorted((readme - claude) & shipped)}, "
        f"CLAUDE seul {sorted((claude - readme) & shipped)}")
