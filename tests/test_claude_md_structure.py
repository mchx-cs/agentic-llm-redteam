"""
La structure de CLAUDE.md, et les chiffres de sa section d'état.

POURQUOI CE FICHIER EXISTE. Ce document a **deux régimes de vérité**, et un
seul rouille. Les entrées datées du journal sont vraies de leur date et ne sont
jamais réécrites — la même raison que les 91 commits français et les 18 pistes
scellées. Les sections d'état, elles, prétendent décrire le PRÉSENT, et chaque
commit qui ne les touche pas les périme en silence.

Le défaut trouvé le 2026-11-26 était structurel et pas seulement de la prose
qui dérive : **le journal n'avait aucun titre à lui.** Ses 6 400 lignes
vivaient sous « What remains », donc la table des matières de GitHub rangeait
toute l'histoire du projet sous un titre qui promet l'état présent — et un
lecteur ne pouvait pas distinguer l'état de l'historique en naviguant.

UN GARDE ÉCRIT PUIS RETIRÉ, et c'est la partie qui vaut d'être lue. J'avais
d'abord interdit toute ENTRÉE DATÉE dans une section d'état, repérée par un
titre en gras portant une date ISO. Mesuré sur le document réel, il était
faux des deux côtés : il attrapait **cinq puces d'état parfaitement
légitimes** (« pass@k is DONE (2026-11-20) » dit l'état d'un item de la liste,
avec sa date), et il MANQUAIT la plupart des vraies entrées, dont le titre
renvoie la date à la ligne suivante. Une date n'est donc pas le discriminant
entre l'état et l'histoire.

Le PLAFOND fait ce travail, et mieux : une entrée de journal fait des dizaines
de lignes, donc elle ne tient pas dans une section capée. Le projet a déjà
retiré un garde entier pour avoir crié faux deux fois sur quatre ; celui-ci
criait faux cinq fois sur cinq.

Ce que ce fichier garde, et la frontière est celle que le projet trace déjà
entre `tests/` et `evaluation/` : ce qui doit être VRAI quoi qu'il arrive. Les
chiffres qui demandent une mesure (les figures du juge, les taux, les
intervalles) n'y sont pas, et un test qui les devinerait serait pire
qu'absent. C'est le pendant de `test_readme_figures.py`, qui tient le compte
de tests du README.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Les sections d'ÉTAT, celles qui rouillent, avec le plafond qu'elles tiennent.
#
# Le plafond n'est pas une coquetterie et il DOIT crier quand on le dépasse :
# une section qui décrit le présent ne doit pas pouvoir grossir, sinon elle
# accumule des affirmations que personne ne relit. Une addition ici déplace
# quelque chose, ou s'écrit dans le journal. C'est l'inverse d'un garde qui
# crie faux — celui-là crie juste, et sa plainte est l'information.
STATE_SECTIONS = {
    "## Current state": 50,
    "## What remains": 240,
}


@pytest.fixture(scope="module")
def document():
    return ROOT.joinpath("CLAUDE.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sections(document):
    """Chaque titre de niveau 2 -> son texte, jusqu'au titre suivant."""
    lines = document.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("## ")]
    out = {}
    for rank, start in enumerate(heads):
        end = heads[rank + 1] if rank + 1 < len(heads) else len(lines)
        out[lines[start]] = "\n".join(lines[start:end])
    return out


@pytest.fixture(scope="module")
def journal(sections):
    titles = [t for t in sections if t.startswith("## Journal")]
    assert titles, "aucune section « ## Journal »"
    return sections[titles[0]]


@pytest.fixture(scope="module")
def state(sections):
    return next(s for t, s in sections.items()
                if t.startswith("## Current state"))


@pytest.fixture(scope="module")
def corpus():
    path = ROOT / "evaluation" / "labelled_exchanges.json"
    return json.loads(path.read_text(encoding="utf-8"))["exchanges"]


def _state_sections(sections):
    """Les sections d'état réellement présentes, par leur préfixe."""
    for prefix, cap in STATE_SECTIONS.items():
        matching = [title for title in sections if title.startswith(prefix)]
        assert len(matching) == 1, (
            f"« {prefix} » devrait exister exactement une fois, trouvé "
            f"{len(matching)} : {matching}")
        yield matching[0], sections[matching[0]], cap


class TestTheJournalIsASectionOfItsOwn:
    """
    Le défaut du 2026-11-26 : 6 400 lignes d'histoire rangées sous un titre
    qui promet l'état présent.
    """

    def test_the_journal_has_a_heading(self, sections):
        titles = [t for t in sections if t.startswith("## Journal")]
        assert titles, (
            "aucun « ## Journal » : les entrées datées seraient rangées sous "
            "une section d'état, et la table des matières de GitHub "
            "présenterait l'historique comme l'état du projet")

    def test_the_journal_says_which_half_of_the_file_rots(self, journal):
        """
        Sans cette phrase, le titre range les entrees sans dire POURQUOI
        elles ne vieillissent pas, et un relecteur << corrigerait >> un
        chiffre date pour le mettre a jour.

        La PHRASE et non le mot : une premiere version cherchait
        << rewritten >>, et la mutation qui retirait la clause restait MUETTE
        parce que la phrase voisine contient le meme mot. Un garde ne vaut que
        ce qu'il COMPARE -- septieme fois dans ce projet.
        """
        opening = journal[:900]
        for claim in ("true of its date", "none is rewritten"):
            assert claim in opening, (
                f"<< {claim} >> absent du titre du journal : il doit dire que "
                f"ses entrees sont vraies de leur date et jamais reecrites, "
                f"sinon quelqu'un les mettra << a jour >>")

    def test_it_holds_MORE_history_than_any_state_section(
            self, journal, sections):
        """
        Une propriete RELATIVE, et c'est deliberement pas un seuil.

        Un seuil absolu ("plus de 20 dates") se regle sur les donnees qu'il
        examine : le mien etait a 20 pour 19 dates reelles, donc un chiffre
        choisi et non une propriete. Ce qui compte n'est pas combien de dates
        le journal porte, c'est qu'il en porte PLUS que les sections d'etat --
        sinon le titre serait la et l'histoire ailleurs, ce qui est le defaut
        d'origine deguise.
        """
        def dates(text):
            return set(re.findall(r"20\d\d-\d\d-\d\d", text))

        here = dates(journal)
        for title, body, _ in _state_sections(sections):
            there = dates(body)
            assert len(here) > len(there), (
                f"<< {title} >> porte {len(there)} date(s) distincte(s) "
                f"contre {len(here)} pour le journal : l'histoire n'est pas "
                f"la ou son titre la promet")

    def test_and_the_journal_is_NOT_capped(self, journal):
        """
        Le contraste, sans lequel les plafonds d'à-côté se liraient comme
        « le fichier ne doit pas grossir ».

        Le journal est le seul endroit qui DOIT croître librement : il
        enregistre ce qui a eu lieu, et ce qui a eu lieu ne se résume pas.
        """
        assert len(journal.splitlines()) > max(STATE_SECTIONS.values()), (
            "si le journal tenait dans le plafond d'une section d'état, il "
            "n'y aurait rien à séparer et ce fichier ne servirait à rien")


class TestTheStateSectionsStayOnAScreen:
    """
    LE GARDE QUI FAIT LE TRAVAIL, après le retrait du garde par date.

    Un plafond ne dit pas seulement « reste court » : il dit OÙ va ce qui est
    écrit. Une entrée de journal fait des dizaines de lignes, donc elle ne
    PEUT pas entrer ici — c'est l'enforcement que le repérage par date
    prétendait faire et faisait mal.
    """

    def test_each_state_section_is_within_its_cap(self, sections):
        for title, body, cap in _state_sections(sections):
            size = len(body.splitlines())
            assert size <= cap, (
                f"« {title} » fait {size} lignes pour un plafond de {cap}.\n"
                f"Ce n'est pas un détail de mise en forme : une section qui "
                f"décrit le présent accumule des affirmations que personne ne "
                f"relit. Déplace quelque chose, ou écris-le sous "
                f"« ## Journal ».")

    def test_the_caps_are_TIGHT_enough_to_refuse_a_journal_entry(
            self, journal):
        """
        Ce qui rend les plafonds utiles plutôt que décoratifs : un plafond
        plus large qu'une entrée typique ne refuserait rien.

        Mesuré sur le journal réel, pas supposé : on compare le plafond à la
        taille d'une entrée moyenne.
        """
        titles = [i for i, line in enumerate(journal.splitlines())
                  if line.startswith("**") and "20" in line]
        assert len(titles) > 10
        typical = len(journal.splitlines()) / len(titles)
        assert max(STATE_SECTIONS.values()) < typical * 12, (
            f"une entrée fait ~{typical:.0f} lignes et le plafond le plus "
            f"large est {max(STATE_SECTIONS.values())} : assez lâche pour "
            f"laisser entrer une poignée d'entrées sans rien dire")

    def test_the_state_section_SAYS_that_it_rots(self, state):
        assert "rots" in state, (
            "la section doit dire d'elle-même qu'elle décrit le présent et "
            "qu'elle se périme : un lecteur dans six mois n'a aucun autre "
            "moyen de le savoir")


class TestTheFiguresTheMachineCanCHECK:
    """
    Les chiffres de la section d'état que CI peut vérifier seule.

    La colonne « guarded? » du tableau n'est pas décorative : les chiffres de
    payloads dépendent de `payloads/garak.json`, qui est gitignoré. Un garde
    sur eux passerait sur une machine de développement et échouerait en
    intégration continue — exactement le défaut qui a mis la CI au rouge
    pendant six jours. Donc on garde ce que CI voit, et on DÉCLARE le reste.
    """

    def test_the_corpus_size_and_its_split(self, state, corpus):
        dev = sum(1 for e in corpus if e["dataset"] == "dev")
        test = sum(1 for e in corpus if e["dataset"] == "test")
        for figure in (f"{len(corpus)}", f"{dev} `dev`", f"{test} `test`"):
            assert figure in state, (
                f"« {figure} » absent de la section d'état : le corpus compte "
                f"{len(corpus)} entrées, {dev} dev et {test} test")

    def test_the_provenance_split(self, state, corpus):
        author = sum(1 for e in corpus if e.get("labelled_by") == "author")
        model = len(corpus) - author
        # La coupe par provenance est la règle de lecture n°1 du projet : une
        # figure sur des étiquettes décidées par un modèle mesure l'accord
        # entre modèles. Un chiffre faux ici trompe sur ce que le corpus EST.
        assert f"**{author}**" in state and f"{model} by a model" in state, (
            f"la section doit annoncer {author} par l'auteur contre {model} "
            f"par un modèle")

    def test_the_four_criteria_are_those_the_DEFAULT_instruction_scores(
            self, state):
        """
        LE DÉFAUT, et non ce que le corpus étiquette. Depuis le 2026-11-26 le
        corpus étiquette pour un cinquième critère qui vit dans le bras
        un bras de côté jusqu'au 2026-11-27 : la section d'état décrit ce
        qu'une campagne ORDINAIRE score,
        donc elle annonce quatre.
        """
        from agents.judge import JUDGE_SYSTEM_PROMPT
        from evaluation.label import CRITERION_OF

        by_default = {c for c in CRITERION_OF.values()
                      if c and f'"{c}"' in JUDGE_SYSTEM_PROMPT}
        # SIX depuis le 2026-11-27 au soir : `fuite_permissions` est
        # entre dans l'instruction livree avec le cinquieme, donc le tableau
        # d'etat doit le nommer aussi. Le chiffre est ici et non derive,
        # pour que l'ajout d'un septieme critere force une decision au lieu
        # d'etre absorbe en silence.
        assert len(by_default) == 6, (
            f"le tableau annonce 6 critères et l'instruction par défaut en "
            f"score {len(by_default)} : {sorted(by_default)}")
        for criterion in by_default:
            assert f"`{criterion}`" in state, (
                f"« {criterion} » est scoré par défaut et n'est pas nommé "
                f"dans la section d'état")

    def test_and_the_judge_can_EMIT_each_of_them(self):
        """
        Un critère que le corpus étiquette et que le juge ne peut pas nommer
        est un faux négatif garanti — la raison pour laquelle
        `fuite_donnees_tiers` n'a pas été ajouté avant son critère.
        """
        from agents.judge import INSTRUCTIONS
        from evaluation.label import CRITERION_OF

        # AU MOINS UN BRAS : le cinquième critère a vécu un jour dans un
        # bras `fr5` et il est dans les deux depuis le 2026-11-27, et la
        # garantie qui compte est qu'aucune étiquette n'existe sans critère
        # quelque part.
        for criterion in {c for c in CRITERION_OF.values() if c}:
            assert any(criterion in prompt
                       for prompt, _ in INSTRUCTIONS.values()), (
                f"« {criterion} » est étiquetable et absent de TOUS les "
                f"bras : le juge ne pourrait jamais le nommer")

    def test_the_payload_figures_DECLARE_themselves_unguarded(self, state):
        """
        Protège une non-garantie, comme le fait le garde qui tient que
        `docs:0` n'est PAS un niveau de livraison déclaré.

        Sans ce test, quelqu'un ajouterait « utilement » un garde sur les
        1 166 payloads, et la CI deviendrait rouge pour une raison
        invisible depuis le dépôt : le snapshot n'y est pas.
        """
        assert "the snapshot is outside git" in state, (
            "le tableau doit dire que les chiffres de payloads ne sont pas "
            "gardés, et pourquoi")
        assert "guard what CI can see" in state, (
            "la règle doit être écrite, pas seulement appliquée")
