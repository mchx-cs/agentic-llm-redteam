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
        "le nombre de tests doit rester écrit avec une virgule, `1,234` "
        "dans cette forme : c'est ce que l'expression du garde reconnaît")


def test_and_the_promise_beside_it_is_still_there(collected):
    """
    Le chiffre ne vaut que par la phrase qu'il quantifie.

    « tests/ never calls a model » est une promesse tenue par un fixture dans
    `tests/test_collect_conversations.py` et par la discipline du projet
    ailleurs. Si elle disparaissait du README, le chiffre resterait vrai et
    ne dirait plus rien.
    """
    assert "never calls a model" in _readme()


def _claude_md():
    return (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


#: La ligne de CLAUDE.md qui prétend décrire l'état ACTUEL, et la seule.
#:
#: Elle visait « - **Phase 10**: N `pytest` tests » jusqu'au 2026-11-26, où la
#: section d'état est passée de 71 lignes à 40 : les huit puces de phase
#: re-décrivaient la roadmap et la carte d'architecture, et leurs chiffres sont
#: devenus un tableau. Le garde a ÉCHOUÉ ce jour-là, ce qui est son travail —
#: il a remarqué que le chiffre avait déménagé.
#:
#: Et la nouvelle forme est plus sûre que l'ancienne : ici le nombre vient
#: APRÈS « `pytest` tests », là où chaque entrée datée du journal l'écrit
#: AVANT. Les deux formes ne peuvent donc plus se confondre, alors que
#: l'ancienne ancre ne tenait que par le mot « Phase 10 ».
STATE_COUNT = re.compile(r"\| `pytest` tests[^|]*\| \*\*([\d,]+)\*\*")


def test_the_CLAUDE_md_header_counts_the_real_tests(collected):
    """
    L'en-tête de CLAUDE.md annonçait 776 tests pour 1 408 le 2026-11-21, et
    trois autres affirmations fausses avec — dont une qui contredisait la
    table de roadmap du même fichier.

    C'est le premier écran lu, y compris par l'assistant au démarrage de
    chaque session : un en-tête périmé désinforme le lecteur ET l'outil.
    """
    found = STATE_COUNT.search(_claude_md())
    assert found, ("le tableau de la section d'état n'annonce plus de nombre "
                   "de tests")
    announced = int(found.group(1).replace(",", ""))
    assert announced == collected, (
        f"CLAUDE.md annonce {announced} tests, pytest en collecte "
        f"{collected}. Corriger l'en-tête, pas ce test.")


def test_and_the_DATED_journal_entries_are_exempt():
    """
    Le piège de ce garde, dit plutôt que laissé à découvrir.

    Chaque entrée du journal finit par « N pytest tests », vrai de SA date.
    Un garde qui les couvrirait toutes échouerait sur le journal entier et
    serait désarmé le jour même — ou pousserait à réécrire des entrées
    datées, ce que ce projet refuse comme il refuse de réécrire les 91
    commits français et les 18 pistes scellées.

    Ce test tient la propriété qui JUSTIFIE l'ancre : il y a bien plusieurs
    chiffres dans le fichier, et ils ne sont pas tous égaux. Sans ça,
    viser la phase 10 serait une précaution décorative.
    """
    every = re.findall(r"([\d,]+) `pytest` tests", _claude_md())
    assert len(every) > 5, (
        "le journal ne porte plus ses comptes datés : l'ancre ciblée n'a "
        "plus de raison d'être")
    assert len(set(every)) > 1, (
        "tous les comptes du fichier sont égaux, donc rien ne distingue "
        "l'en-tête d'une entrée datée — ce garde ne comparerait rien")


def test_the_header_does_not_contradict_the_ROADMAP_table():
    """
    La contradiction trouvée le 2026-11-21, et elle était interne au fichier.

    Le titre annonçait « 2, 3b and 5 in progress » quand la table de roadmap,
    deux cents lignes plus bas, marque 3b **Done** — mesuré négativement.
    Un lecteur qui survole le titre n'avait pas la même histoire qu'un
    lecteur qui lit la table, et c'est la forme de défaut que ce projet
    traque le plus souvent.
    """
    text = _claude_md()
    title = [line for line in text.splitlines()
             if line.startswith("## Current state")]
    assert len(title) == 1, "l'en-tête d'état a disparu ou s'est dupliqué"

    # Les phases que le TITRE dit ouvertes, et celles que la TABLE dit
    # ouvertes, doivent être les mêmes. La table est la source : elle porte
    # le statut phase par phase.
    open_in_table = {
        row.split("|")[1].strip()
        for row in text.splitlines()
        if re.match(r"^\| [0-9]+[ab]? \|", row) and "In progress" in row}
    for phase in open_in_table:
        assert phase in title[0], (
            f"la table dit la phase {phase} ouverte, le titre ne la nomme "
            f"pas : {title[0]}")
    for named in re.findall(r"\b([0-9]+[ab]?)\b", title[0].split(":", 1)[1]):
        if named in {"14"}:        # le compte de phases closes
            continue
        assert named in open_in_table, (
            f"le titre dit la phase {named} ouverte, la table ne la marque "
            f"pas « In progress »")


def test_the_TWO_roadmaps_agree_on_what_is_open():
    """
    CLAUDE.md et le README portent chacun une table de roadmap, tenue à la
    main, et rien ne les lie. Elles ont déjà divergé le 2026-11-17, où il a
    fallu corriger « both roadmaps, 3b ».

    Ce sont les phases OUVERTES qui sont comparées, pas la prose des
    cellules : les deux documents ne formulent pas pareil et n'ont pas le
    même détail, et exiger l'égalité du texte serait un garde qui crie faux
    à chaque reformulation — ce que ce projet a déjà retiré un garde pour
    avoir fait.
    """
    def open_phases(text):
        found = set()
        for line in text.splitlines():
            cells = [cell.strip() for cell in line.split("|")]
            if len(cells) < 4:
                continue
            phase = cells[1].strip("*").strip()
            if re.fullmatch(r"[0-9]+[ab]?", phase) and "In progress" in line:
                found.add(phase)
        return found

    in_claude = open_phases(_claude_md())
    in_readme = open_phases(_readme())
    assert in_claude, "CLAUDE.md ne marque plus aucune phase ouverte"
    assert in_claude == in_readme, (
        f"les deux roadmaps divergent : CLAUDE.md ouvre {sorted(in_claude)}, "
        f"le README {sorted(in_readme)}")


def test_the_README_corpus_figures_are_the_real_ones():
    """
    LES MEMES CHIFFRES QUE CLAUDE.md, et ils etaient gardes d'un seul cote.

    Le bloc d'ouverture du README -- les deux premieres phrases qu'un visiteur
    lit -- annoncait la taille du corpus et sa coupe de provenance sans aucun
    garde, tandis que `test_claude_md_structure` les verifiait deja. Mesure le
    2026-11-26 : il disait encore 256 / 139 quand le corpus en portait
    277 / 160.

    C'est le seul endroit du README ou un chiffre de corpus est cite, et c'est
    celui qu'un lecteur ne peut pas verifier lui-meme. Le corpus est COMMITTE,
    donc l'integration continue le voit : la regle << garder ce que CI voit,
    DECLARER ce qu'elle ne voit pas >> autorise ce garde, la ou les chiffres de
    payloads restent declares.

    La PROVENANCE est la raison pour laquelle ce chiffre compte : une figure
    sur des etiquettes decidees par un modele mesure l'accord entre modeles.
    Annoncer un corpus plus << humain >> qu'il n'est serait mentir sur
    exactement ce point.
    """
    import json
    import re

    corpus = json.loads(
        (ROOT / "evaluation" / "labelled_exchanges.json").read_text(
            encoding="utf-8"))["exchanges"]
    by_author = sum(1 for entry in corpus
                    if entry["labelled_by"] == "author")
    by_model = sum(1 for entry in corpus if entry["labelled_by"] == "model")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    found = re.search(
        r"(\d[\d,]*) labelled exchanges\s*—\s*(\d[\d,]*) labelled by the "
        r"author, (\d[\d,]*) by a model", readme)
    assert found, (
        "la phrase qui annonce le corpus a change de forme : ce garde ne "
        "compare plus rien. La corriger, pas le supprimer.")
    announced = [int(group.replace(",", "")) for group in found.groups()]
    assert announced == [len(corpus), by_author, by_model], (
        f"le README annonce {announced}, le corpus porte "
        f"{[len(corpus), by_author, by_model]}. Corriger le README, pas ce "
        f"test.")


def test_the_attack_surface_table_names_EVERY_criterion():
    """
    LE TABLEAU DE LA VITRINE CONTRE `report.SEVERITIES`, et il ne nommait que
    TROIS criteres sur six -- trouve par Clement, pas par un test.

    `fuite_donnees_tiers` (2026-11-18), `fingerprinting` (11-26) et
    `fuite_permissions` (11-27) manquaient tous les trois. La colonne
    << Judge criterion >> est au SINGULIER : elle supposait une relation 1
    pour 1 entre famille OWASP et critere, qui n'existe plus depuis que LLM02
    en porte deux.

    Ce tableau est l'endroit du README qui DIT a un lecteur ce que l'arbitre
    sait noter. Un critere absent s'y lit comme un registre que l'outil ne
    couvre pas -- une SOUS-estimation, le miroir de la surestimation que le
    reste du document combat.

    On compare a `SEVERITIES`, et non a une liste ecrite a la main : c'est la
    porte que la severite franchit, donc l'ensemble des criteres qu'un rapport
    peut vraiment GRADER. Meme forme que le garde de completude de la table de
    severite, et pour la meme raison -- une liste a la main ne voit pas
    arriver un septieme critere.
    """
    import report

    readme = _readme()
    start = readme.index("## Attack surface targeted")
    # BORNE : le tableau s'arrete a la premiere ligne qui n'est pas une
    # rangee. Sans elle, le balayage ramassait le tableau de reference du
    # cablage de cible, 1 000 lignes plus bas -- defaut de mon propre garde,
    # trouve a son premier lancement.
    after = readme[start:].splitlines()
    first = next(i for i, line in enumerate(after) if line.startswith("|"))
    rows = []
    for line in after[first:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    assert len(rows) > 3, (
        "le tableau de la surface d'attaque ne se reconnait plus a des lignes "
        "`|` sous son titre : ce garde ne compare plus rien. Corriger la "
        "lecture, pas le supprimer.")

    named = set()
    for row in rows[2:]:            # [0] l'en-tete, [1] le separateur
        last = row.rstrip("|").rsplit("|", 1)[-1].strip()
        if last.startswith("`") and last.endswith("`"):
            named.add(last.strip("`"))

    graded = {criterion for criterion, _ in report.SEVERITIES}
    assert named == graded, (
        f"le tableau nomme {sorted(named)}, le juge grade {sorted(graded)}. "
        f"Manquants : {sorted(graded - named)} ; inconnus du code : "
        f"{sorted(named - graded)}. Corriger le README, pas ce test.")


def test_and_the_sentence_beside_it_carries_the_REAL_counts():
    """
    LES DEUX CHIFFRES DE CETTE PHRASE, et ils ne disent pas la meme chose.

    << Six criteria across four families >> est l'affirmation qui explique
    pourquoi elargir les criteres n'a PAS elargi la couverture. Les deux
    moities se perimnent separement : un septieme critere qui refine une
    famille deja couverte bouge la premiere et pas la seconde, et c'est
    exactement ce qui est arrive deux fois le 2026-11-26 et le 11-27.

    Les familles comptees sont celles que `ATLAS_BY_FAMILY` porte -- les
    quatre pour lesquelles un identifiant source existe -- et non les dix du
    Top 10 ni les trois etats de couverture du rapport.
    """
    import re

    import report

    found = re.search(
        r"\*\*(\w+) criteria across (\w+) families", _readme())
    assert found, (
        "la phrase qui explique six criteres pour quatre familles a change de "
        "forme : ce garde ne compare plus rien. La corriger, pas le "
        "supprimer.")

    WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    announced = [WORDS.get(word.lower()) for word in found.groups()]
    assert None not in announced, (
        f"un des deux nombres n'est pas ecrit en mots : {found.groups()}")

    real = [len({criterion for criterion, _ in report.SEVERITIES}),
            len(report.ATLAS_BY_FAMILY)]
    assert announced == real, (
        f"le README annonce {announced} (criteres, familles), le code porte "
        f"{real}. Corriger le README, pas ce test.")
