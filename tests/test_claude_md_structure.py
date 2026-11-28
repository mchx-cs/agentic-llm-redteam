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

import hashlib
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
    # AJOUTE LE 2026-11-28, ET C'EST LA CORRECTION STRUCTURELLE DU JOUR.
    # « Decisions taken » etait une section en FORME d'etat -- son titre
    # promet « voici les decisions » -- et c'etait la seule a n'avoir aucun
    # plafond. Elle a atteint 4 083 lignes, 88 % du fichier une fois le
    # journal sorti. Les deux sections capees ne l'ont pas fait. Le pointeur
    # qui la remplace est donc cape comme ses voisines, parce qu'un renvoi
    # qui se remet a accumuler redevient la section qu'il remplace.
    "## Decisions taken": 40,
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


#: Le journal est un REPERTOIRE depuis le 2026-11-28, un fichier par jour.
JOURNAL_DIR = ROOT / "docs" / "journal"

#: Le sha256 du corps du journal tel qu'il etait dans CLAUDE.md juste avant
#: le decoupage. C'est la seule chose qui rend « rien n'a ete perdu »
#: verifiable : un octet de derive et la suite tombe.
JOURNAL_SHA = (
    "4860acb178b2fbaadb5d89af614be40ce7f06ce7752c0326887f141b8459e309")

#: Les decisions sont un FICHIER depuis le 2026-11-28, et ce digest porte sur
#: les octets deplaces : la queue de `docs/decisions.md`, apres la sentinelle.
DECISIONS_FILE = ROOT / "docs" / "decisions.md"
DECISIONS_SHA = (
    "5583df491cc24dcee058637503367ab3eab35e0960162a38424afb65e12f6d8d")

#: LA SENTINELLE EST DANS LE FICHIER, PAS ICI, et c'est deliberé : la
#: frontiere entre ce qui a ete reecrit et ce qui a ete deplace devient un
#: fait du document, visible par un lecteur humain, au lieu d'une convention
#: que seul ce garde connaitrait.
DECISIONS_MARK = "MOVED VERBATIM FROM CLAUDE.md ON 2026-11-28"


@pytest.fixture(scope="module")
def pointer(sections):
    """La section « ## Journal » de CLAUDE.md : le preambule et le renvoi."""
    titles = [t for t in sections if t.startswith("## Journal")]
    assert titles, "aucune section « ## Journal »"
    return sections[titles[0]]


@pytest.fixture(scope="module")
def day_files():
    """Les fichiers du jour, par date croissante."""
    found = sorted(JOURNAL_DIR.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
    assert found, (
        f"aucun fichier de jour dans {JOURNAL_DIR} : le journal a disparu, "
        f"ou son nommage a change et ce fichier ne compare plus rien")
    return found


@pytest.fixture(scope="module")
def journal(day_files):
    """Tout le journal, concatene -- la population que ces gardes mesurent."""
    return "\n".join(p.read_text(encoding="utf-8") for p in day_files)


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

    def test_the_journal_says_which_half_of_the_file_rots(self, pointer):
        """
        Sans cette phrase, le titre range les entrees sans dire POURQUOI
        elles ne vieillissent pas, et un relecteur << corrigerait >> un
        chiffre date pour le mettre a jour.

        La PHRASE et non le mot : une premiere version cherchait
        << rewritten >>, et la mutation qui retirait la clause restait MUETTE
        parce que la phrase voisine contient le meme mot. Un garde ne vaut que
        ce qu'il COMPARE -- septieme fois dans ce projet.
        """
        # L'ESPACE EST A NOUS, LES MOTS SONT LA REVENDICATION : une
        # premiere version comparait le texte brut, donc un retour a la
        # ligne tombant entre « true of » et « its date » la faisait
        # echouer sur une phrase parfaitement presente. C'est la methode de
        # `check_excerpt.py`, et elle vaut ici pour la meme raison.
        opening = " ".join(pointer[:1400].split())
        for claim in ("true of its date", "none is rewritten"):
            assert claim in opening, (
                f"<< {claim} >> absent du titre du journal : il doit dire que "
                f"ses entrees sont vraies de leur date et jamais reecrites, "
                f"sinon quelqu'un les mettra << a jour >>")

    def test_and_it_SAYS_where_the_entries_live(self, pointer, day_files):
        """
        LE RENVOI, et sans lui le titre promet une histoire qu'il ne porte
        plus. Un lecteur de `CLAUDE.md` doit pouvoir aller la lire sans
        deviner, et un chemin qui ne resout pas est pire qu'absent.
        """
        assert "docs/journal/" in pointer, (
            "la section « ## Journal » ne renvoie plus vers "
            "`docs/journal/` : ses entrees sont ailleurs et rien ne le dit")
        assert (JOURNAL_DIR / "README.md").exists(), (
            "pas d'index dans docs/journal/ : dix fichiers de dates sans "
            "table de matieres, ce qui est le defaut que le decoupage "
            "existait pour corriger")
        announced = len(day_files)
        assert f"{announced} days" in pointer or \
               f"{announced} working days" in pointer, (
            f"le renvoi n'annonce pas les {announced} jours reellement "
            f"presents : corriger CLAUDE.md, pas ce test")

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

    def test_and_the_journal_is_NOT_capped(self, day_files):
        """
        Le contraste, sans lequel les plafonds d'à-côté se liraient comme
        « le fichier ne doit pas grossir ».

        Le journal est le seul endroit qui DOIT croître librement : il
        enregistre ce qui a eu lieu, et ce qui a eu lieu ne se résume pas.
        """
        biggest = max(len(p.read_text(encoding="utf-8").splitlines())
                      for p in day_files)
        assert biggest > max(STATE_SECTIONS.values()), (
            f"le plus gros fichier de jour fait {biggest} lignes, sous le "
            f"plafond le plus large ({max(STATE_SECTIONS.values())}) : si une "
            f"journee entiere tenait dans une section d'etat, il n'y aurait "
            f"rien a separer et ce fichier ne servirait a rien")


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


class TestTheMoveOf20261128LostNothing:
    """
    << RIEN N'A ETE PERDU >> EST UNE PROPRIETE, PAS UNE AFFIRMATION.

    Le 2026-11-28 le journal a quitte `CLAUDE.md` -- 11 170 lignes, 69 %
    d'un fichier de 900 Ko charge en entier a chaque session, contre 3 % qui
    sont vraiment une instruction. Les entrees ont ete DEPLACEES et jamais
    reecrites, ce que la regle du projet impose : une entree est vraie de sa
    date.

    Donc le garde reconcatene et compare au sha256 du texte qui etait la.
    Relire le resultat ne prouverait rien -- ce projet a enregistre assez de
    defauts muets pour savoir qu'une relecture n'est pas une preuve -- et
    c'est la forme que `audit.py` emploie deja pour une piste scellee : si le
    contenu bouge, le digest le dit.

    CE QUE LE GARDE NE TIENT PAS, et il faut le dire : il n'interdit pas
    d'AJOUTER une entree. Un jour neuf change la concatenation, donc le
    digest cesse de correspondre -- et c'est pour ca qu'il porte sur le
    PREFIXE historique et non sur la totalite. La frontiere est le dernier
    jour migre, nomme ici.
    """

    #: Le dernier jour present au moment du decoupage. Ce qui est ecrit
    #: APRES n'entre pas dans le digest, sinon le garde interdirait au
    #: journal de croitre -- exactement ce que le non-plafonnement dit.
    LAST_MIGRATED = "2026-11-27"

    def test_the_migrated_days_reassemble_to_the_ORIGINAL_bytes(
            self, day_files):
        migrated = [p for p in day_files if p.stem <= self.LAST_MIGRATED]
        assert migrated, "aucun jour migre : le garde ne compare plus rien"

        pieces = []
        for path in migrated:
            body = path.read_text(encoding="utf-8")
            head = f"# Journal — {path.stem}\n\n"
            assert body.startswith(head), (
                f"{path.name} n'ouvre plus sur « {head.strip()} » : le "
                f"garde retire un en-tete qu'il connait exactement, donc "
                f"un en-tete different fausserait la comparaison")
            pieces.append(body[len(head):])

        # LE DIGEST PORTE SUR LES ENTREES, ET PAS SUR LE PREAMBULE, pour
        # une raison qui est un fait et non une commodite : le preambule a
        # ete REECRIT au deplacement, parce qu'il ouvrait sur « Everything
        # BELOW is dated » et que plus rien n'est en dessous. Le garder
        # verbatim aurait garde une phrase fausse dans une section d'etat.
        #
        # Ses 803 octets d'origine ne sont pas perdus : ils sont cites
        # verbatim dans `docs/journal/README.md`, et un garde voisin le
        # verifie. Ce qui est couvert par une preuve est donc exactement ce
        # que la regle protege -- les entrees, vraies de leur date.
        rebuilt = "".join(pieces)

        digest = hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
        assert digest == JOURNAL_SHA, (
            f"LA MIGRATION A PERDU OU ALTERE DU TEXTE.\n"
            f"  reconstruit : {len(rebuilt)} octets, sha {digest}\n"
            f"  attendu     : sha {JOURNAL_SHA}\n"
            f"Les entrees datees ne se reecrivent pas : une entree est vraie "
            f"de sa date. Si une correction etait voulue, elle s'ecrit comme "
            f"une entree NEUVE et ce digest reste celui de l'original.")

    def test_and_the_digest_is_the_one_CLAUDE_md_publishes(self, pointer):
        """
        LA JONCTION, et c'est la forme de defaut la plus frequente ici : le
        garde pourrait comparer au bon digest pendant que `CLAUDE.md` en
        annonce un autre, et un lecteur n'aurait aucun moyen de verifier.
        """
        assert JOURNAL_SHA[:16] in pointer, (
            f"CLAUDE.md n'annonce plus le digest que ce garde verifie "
            f"({JOURNAL_SHA[:16]}…) : la revendication et sa preuve ont "
            f"divergé")

    #: Le sha256 du paragraphe qui introduisait les entrees dans CLAUDE.md
    #: jusqu'au 2026-11-28. C'est la SEULE partie du deplacement qui a ete
    #: reecrite -- elle ouvrait sur « Everything BELOW is dated », rendu faux
    #: par le decoupage -- donc la seule qui devait etre preservee ailleurs
    #: qu'en la deplacant.
    PREAMBLE_SHA = (
        "8583cf8ce148d78cfc947175aada40ea953a9c89473f58a34f039a0a873ebd30")

    def test_the_REWRITTEN_preamble_is_preserved_verbatim(self):
        """
        ET LA PREMIERE VERSION DE CE GARDE SE SATISFAISAIT DE MA PROSE.

        Elle cherchait trois PHRASES dans tout l'index, et l'une d'elles --
        « Everything below is dated » -- est dans le paragraphe ou j'explique
        pourquoi elle est devenue fausse. Donc retirer la citation preservee
        ne faisait rien echouer : le garde lisait le commentaire a la place
        de la preuve. Trouve par mutation, treizieme fois dans ce projet
        qu'un garde ne vaut que ce qu'il COMPARE.

        D'ou le BLOC DE CITATION et son digest, plutot qu'une meilleure
        recherche de phrases : « preserve verbatim » est une egalite, donc le
        garde doit comparer une egalite.
        """
        index = (JOURNAL_DIR / "README.md").read_text(encoding="utf-8")

        quoted = [line for line in index.splitlines()
                  if line.startswith(">")]
        assert quoted, (
            "aucun bloc de citation dans docs/journal/README.md : le "
            "preambule d'origine n'y est plus, et c'etait la seule partie "
            "REECRITE du deplacement du 2026-11-28")

        restored = "\n".join(
            line[2:] if line.startswith("> ") else line[1:]
            for line in quoted).strip()
        digest = hashlib.sha256(restored.encode("utf-8")).hexdigest()
        assert digest == self.PREAMBLE_SHA, (
            f"LA CITATION N'EST PLUS LE PREAMBULE D'ORIGINE.\n"
            f"  cite    : {len(restored)} octets, sha {digest}\n"
            f"  attendu : sha {self.PREAMBLE_SHA}\n"
            f"Il a ete reecrit dans CLAUDE.md parce qu'une de ses phrases y "
            f"devenait fausse ; sa version d'origine n'existe donc plus "
            f"qu'ici, et une citation approximative la perd.")

        # ET LE COMPTE ANNONCE A COTE, parce qu'il a ete FAUX. Les deux
        # documents disaient « 803 bytes » pour une citation qui en fait
        # 745 : le chiffre avait ete ecrit avant que la citation soit
        # normalisee, et il est reste. Le digest tenait le CONTENU et
        # personne ne tenait le COMPTE -- un garde ne vaut que ce qu'il
        # compare, et il ne comparait pas celui-la.
        for name, doc in (("CLAUDE.md", ROOT / "CLAUDE.md"),
                          ("l'index", JOURNAL_DIR / "README.md")):
            body = doc.read_text(encoding="utf-8")
            assert f"{len(restored)} bytes" in body, (
                f"{name} n'annonce pas les {len(restored)} octets que la "
                f"citation fait reellement : un compte faux a cote d'un "
                f"digest juste se lit comme verifie alors qu'il ne l'est "
                f"pas")

    def test_every_day_file_is_named_by_a_DATE_it_contains(self, day_files):
        """
        Un fichier nomme `2026-11-19.md` dont les entrees sont du 20 serait
        un decoupage faux qui se lit juste. Mesure plutot que suppose.
        """
        for path in day_files:
            body = path.read_text(encoding="utf-8")
            assert path.stem in body, (
                f"{path.name} ne contient pas sa propre date : le "
                f"regroupement par jour a mis une entree dans le mauvais "
                f"fichier")
class TestTheDECISIONSMoveLostNothing:
    """
    LE MEME INVARIANT QUE POUR LE JOURNAL, SUR UNE AUTRE POPULATION.

    Le 2026-11-28, apres le journal, << Decisions taken, and why >> a quitte
    `CLAUDE.md` a son tour : 4 076 lignes, 88 % de ce que le premier
    deplacement avait laisse. Elles ont ete DEPLACEES en bloc, sans tri,
    parce que la frontiere durable/date demande une lecture par bloc qui est
    l'intention de l'auteur et pas une regle -- le meme principe que le
    partage dev/test, ou ce qui decide est l'intention declaree et jamais le
    texte.

    DONC RIEN NE JUSTIFIE UNE RELECTURE : si rien n'a ete trie ni reecrit, la
    propriete est une EGALITE, et elle se verifie comme telle.
    """

    def test_the_moved_bytes_are_IDENTICAL_to_what_CLAUDE_md_held(self):
        assert DECISIONS_FILE.exists(), (
            "docs/decisions.md a disparu : CLAUDE.md renvoie vers un "
            "fichier absent, ce qui est pire qu'une section trop longue")
        text = DECISIONS_FILE.read_text(encoding="utf-8")

        halves = text.split(DECISIONS_MARK, 1)
        assert len(halves) == 2, (
            f"la sentinelle << {DECISIONS_MARK} >> n'est plus dans "
            f"docs/decisions.md : plus rien ne dit ou s'arrete le cadre "
            f"reecrit et ou commencent les octets deplaces")
        # LA FRONTIERE EST ECRITE DANS LES OCTETS QUE LE FICHIER PORTE, et
        # la premiere version de cette ligne ne l'etait pas : elle coupait
        # sur « -->\n » et mangeait donc le premier retour a la ligne des
        # octets deplaces. Le garde a mordu sur UN octet, ce qui est son
        # travail -- mais le tort etait le sien et pas celui du fichier. On
        # coupe apres la fermeture du commentaire, rien de plus.
        tail = halves[1].split("-->", 1)[1]

        digest = hashlib.sha256(tail.encode("utf-8")).hexdigest()
        assert digest == DECISIONS_SHA, (
            f"LE DEPLACEMENT A PERDU OU ALTERE DU TEXTE.\n"
            f"  trouve  : {len(tail)} octets, sha {digest}\n"
            f"  attendu : sha {DECISIONS_SHA}\n"
            f"Ces blocs ont ete deplaces en bloc et jamais reecrits. Si une "
            f"correction est voulue, elle s'ecrit comme une entree NEUVE "
            f"dans docs/journal/, et ce digest reste celui de l'original.")

    def test_and_the_digest_is_the_one_CLAUDE_md_publishes(self, sections):
        """
        LA JONCTION, dixieme fois que ce projet la rencontre : le garde peut
        comparer au bon digest pendant que `CLAUDE.md` en annonce un autre,
        et un lecteur n'aurait alors aucun moyen de verifier la revendication
        qu'il lit.
        """
        titles = [t for t in sections if t.startswith("## Decisions taken")]
        assert titles, "aucune section « ## Decisions taken » dans CLAUDE.md"
        body = sections[titles[0]]
        assert DECISIONS_SHA[:16] in body, (
            f"CLAUDE.md n'annonce plus le digest que ce garde verifie "
            f"({DECISIONS_SHA[:16]}…) : la revendication et sa preuve ont "
            f"divergé")
        assert "docs/decisions.md" in body, (
            "la section ne renvoie plus vers `docs/decisions.md` : les "
            "decisions sont ailleurs et rien ne dit ou")

    #: Le sha256 du paragraphe qui introduisait les decisions dans CLAUDE.md
    #: jusqu'au 2026-11-28. Comme pour le journal, c'est la seule partie
    #: REECRITE -- il disait « they are not moved », ce que ce deplacement a
    #: rendu faux, et comptait « 39 dated entries », mesure faux la veille.
    PREAMBLE_SHA = (
        "6613802b23e2764b3ce38f9b1d1b3782fd088996fb86a6df1291f83aa0c98155")

    def test_the_REWRITTEN_preamble_is_preserved_verbatim(self):
        """
        DEUX PHRASES DEVENUES FAUSSES, donc un cadre reecrit, donc un
        original a preserver ailleurs qu'en le deplacant.

        Et le garde compare une EGALITE plutot que de chercher des phrases :
        la premiere version de son jumeau, cote journal, se satisfaisait de
        ma propre prose, parce que la phrase qu'elle cherchait figurait dans
        le paragraphe ou j'expliquais pourquoi elle etait devenue fausse.
        """
        text = DECISIONS_FILE.read_text(encoding="utf-8")
        frame = text.split(DECISIONS_MARK, 1)[0]

        quoted = [ln for ln in frame.splitlines() if ln.startswith(">")]
        assert quoted, (
            "aucun bloc de citation avant la sentinelle : le preambule "
            "d'origine n'est plus preserve, et c'etait la seule partie "
            "REECRITE du deplacement")

        restored = "\n".join(
            ln[2:] if ln.startswith("> ") else ln[1:]
            for ln in quoted).strip()
        digest = hashlib.sha256(restored.encode("utf-8")).hexdigest()
        assert digest == self.PREAMBLE_SHA, (
            f"LA CITATION N'EST PLUS LE PREAMBULE D'ORIGINE.\n"
            f"  cite    : {len(restored)} octets, sha {digest}\n"
            f"  attendu : sha {self.PREAMBLE_SHA}\n"
            f"Il a ete reecrit parce que deux de ses phrases devenaient "
            f"fausses ; sa version d'origine n'existe donc plus qu'ici, et "
            f"une citation approximative la perd.")

    def test_the_file_SAYS_which_of_its_halves_rots(self):
        """
        LA PHRASE SANS LAQUELLE LE FICHIER MENT PAR OMISSION, et c'est le
        motif que ce projet a rencontre seize fois : un document qui ne dit
        pas de quand datent ses chiffres les fait lire comme le present.

        Ici le melange est reel -- une decision ne rouille pas, un compte de
        tests oui -- donc le fichier doit le DECLARER. Compare sur les mots
        et non sur le texte brut : l'espace est a nous, les mots sont la
        revendication, la methode de `check_excerpt.py`.
        """
        text = DECISIONS_FILE.read_text(encoding="utf-8")
        frame = " ".join(text.split(DECISIONS_MARK, 1)[0].split())
        for claim in ("read a figure here as dated",
                      "MOVED, never rewritten",
                      # LES TROIS COUTURES MESUREES LE 2026-11-28, que le
                      # digest interdit de corriger sur place : les renvois
                      # deictiques dont le referent a change, les 21 liens de
                      # commit qui n'ont jamais resolu, et l'absence de
                      # titres. Un fichier qui les taisait serait illisible
                      # a l'endroit precis ou il se croit verifie.
                      'mean `CLAUDE.md` as it',
                      "The commit links do not resolve",
                      "finding a decision is a SEARCH"):
            assert " ".join(claim.split()) in frame, (
                f"<< {claim} >> absent du cadre de docs/decisions.md : "
                f"sans cette declaration un lecteur prend un chiffre de 2026 "
                f"pour l'etat present, ce qui est le defaut que la separation "
                f"des deux regimes existe pour empecher")
class TestNoRULEWasOrphanedByTheMoves:
    """
    LE SEUL DEFAUT GRAVE QUE LES DEUX DEPLACEMENTS POUVAIENT CAUSER.

    Le reste du bilan du 2026-11-28 est de la lisibilite : des renvois
    deictiques dont le referent a change, des liens deja casses, l'absence de
    titres. Tout cela se declare. Mais une REGLE que l'agent doit suivre, si
    elle part dans un fichier qui n'est plus charge a chaque session, cesse
    d'etre lue -- et le fichier a alors cesse d'etre reutilisable au sens
    fort.

    IL Y EN AVAIT UNE, trouvee par balayage du normatif : << Fictional
    secrets only >>, une regle de depot PUBLIC, que ni les quatre regles
    survivantes ni `## Legal framing` ne disaient. Elle etait mal classee
    depuis le debut -- une regle qu'on suit, rangee parmi les decisions qu'on
    raconte -- et le deplacement n'a fait que le reveler.

    CE GARDE NE LISTE PAS LES REGLES, il tient leurs SUJETS. Une liste de
    phrases exactes casserait au premier reformulage et passerait sur une
    regle retiree ; un sujet absent est ce qui compte.
    """

    #: Ce qu'un agent ne peut PAS deduire du code et doit donc lire. Chaque
    #: entree est un sujet, avec plusieurs formulations acceptees : ce qui
    #: est garde est que le sujet soit DIT, pas qu'il le soit ainsi.
    RULES = {
        "l'appel indirect aux modeles": ("ask_llm()",),
        "les boucles bornees": ("bound your loops", "MAX_ATTEMPTS"),
        "le jeu gele": ("tune the judge against the test set",),
        "les cles d'API": ("API key in the code", "API keys"),
        "les secrets fictifs": ("Fictional secrets only", "fictional"),
        "l'autorisation ecrite": ("explicitly authorised", "authorisation"),
    }

    def test_every_rule_an_agent_must_FOLLOW_is_still_in_CLAUDE_md(
            self, document):
        missing = [
            subject for subject, forms in self.RULES.items()
            if not any(form in document for form in forms)]
        assert not missing, (
            f"REGLE(S) ORPHELINE(S) : {missing}.\n"
            f"Elles ont quitte CLAUDE.md, donc l'agent ne les lit plus a "
            f"chaque session. Une regle vit dans le fichier charge, jamais "
            f"dans un fichier vers lequel il renvoie -- c'est la difference "
            f"entre une regle et une decision, et c'est ce que les "
            f"deplacements du 2026-11-28 ont failli perdre.")

    def test_and_the_RULES_section_is_where_they_live(self, sections):
        """
        LA JONCTION : une regle presente ailleurs dans le fichier -- dans la
        carte d'architecture, dans un titre de section -- satisferait le
        garde ci-dessus sans etre une regle pour autant. Celui-la verifie
        qu'elles sont bien sous le titre qui les annonce.
        """
        titles = [t for t in sections if t.startswith("## Rules")]
        assert titles, "la section « ## Rules that MUST be respected » a disparu"
        body = sections[titles[0]]

        here = ("ask_llm()", "bound your loops",
                "tune the judge against the test set",
                "API key in the code", "Fictional secrets only")
        absent = [claim for claim in here if claim not in body]
        assert not absent, (
            f"ces regles ne sont plus dans la section des REGLES : "
            f"{absent}. Elles peuvent etre ailleurs dans le fichier et le "
            f"garde voisin passerait quand meme ; une regle rangee ailleurs "
            f"qu'avec les regles se lit comme une anecdote.")
