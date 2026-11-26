"""
Tests for the single-turn harvest (2026-11-20).

Four defects, three of them already fixed in the SIBLING collector and left
standing here — which is the pattern worth naming: `collect_conversations`
was corrected on 2026-11-13 and the correction never crossed the two files.

No LLM call: the target is a function, and the garak snapshot is pinned away
so the pool is KNOWN rather than whatever a local sync happens to hold.
"""

import json

import pytest

import evaluation.collect_exchanges as harvest
from targets import secret_of


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("GARAK_FILE", str(tmp_path / "absent.json"))
    monkeypatch.setattr(harvest, "OUTPUT_FILE", tmp_path / "to_label.json")
    for module in ("llm_client", "agents.judge"):
        monkeypatch.setattr(
            f"{module}.ask_llm",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("modèle appelé depuis tests/")),
            raising=False)


def _target(reply="Je ne peux pas."):
    sent = []

    def ask(message, history=None):
        sent.append(message)
        return reply

    return ask, sent


@pytest.fixture(autouse=True)
def no_model_call(monkeypatch):
    """
    Tout appel a un modele depuis ce fichier doit LEVER.

    Ajoutee le 2026-11-27, quand la reconnaissance a ete cablee dans ce
    collecteur : ses tests sont devenus dependants d'un modele et passaient
    quand meme, parce qu'Ollama tourne sur la machine de developpement. En
    integration continue ils tomberaient tous.

    C'est le piege arme une SECONDE fois -- le collecteur de conversations l'a
    rencontre le 2026-11-13 -- et la lecon est la meme : un environnement de
    developpement plus riche que la CI masque les dependances qu'on vient
    d'ajouter. La regle << un test qui appellerait un modele n'a rien a faire
    dans tests/ >> etait tenue par le code la-bas et par rien ici.
    """
    def refuser(*_, **__):
        raise AssertionError(
            "appel a un modele depuis tests/ : interdit. Passe "
            "`harmless=True` ou neutralise la reconnaissance.")

    for module in ("llm_client", "agents.reconnaissance", "agents.judge"):
        monkeypatch.setattr(f"{module}.ask_llm", refuser, raising=False)



class TestItIsBOUNDED:
    """
    The library crosses to thousands of combinations; at two samples each the
    harvest reached **18,536 entries and 33 MB**, and `label.py` once opened
    on entry 25 of 18,515. A harvest nobody will label is not a harvest, and
    labelling is the scarce resource.
    """

    def test_the_limit_is_respected(self, monkeypatch):
        ask, sent = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        # `harmless` : ce test tient l'ECHANTILLONNAGE, pas le choix des
        # objectifs. Sans lui, son compte dependrait de RECON_BUDGET, qui
        # n'a rien a voir avec la propriete affirmee.
        harvest.collect(target_name="mock", limit=4, harmless=True)
        assert len(sent) == 4 * harvest.SAMPLE_COUNT

    def test_it_does_not_send_the_whole_library(self, monkeypatch):
        from agents.attacker import generate_payloads

        ask, sent = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="mock")
        assert len(sent) < len(generate_payloads()), (
            "the default must bound: the unbounded version produced 18,536 "
            "entries, which is a landfill and not a corpus")

    def test_the_policy_is_ONE_visible_number(self):
        # The sampling choice belongs to whoever decides what the corpus
        # should contain, so it has to be legible: a constant and a flag, not
        # a rule buried in the loop.
        assert isinstance(harvest.MAX_PAYLOADS, int)
        assert harvest.MAX_PAYLOADS > 0

    def test_the_sample_rotates_over_TECHNIQUES(self, monkeypatch):
        """
        Variety is what a corpus needs, so the harvest round-robins instead of
        taking the first N of a sorted list — which would spend the whole
        budget inside one technique. The function is the planner's own, read
        rather than restated.
        """
        from agents.attacker import generate_payloads

        kept = harvest._sample(generate_payloads(), 6)
        assert len({payload["technique"] for payload in kept}) > 1


class TestItAPPENDS:
    """
    The sibling was changed to append for a recorded reason: the corpus needs
    several targets and several defence levels, so it takes several commands,
    and overwriting would erase the previous harvest "and an evening of
    labelling with it".
    """

    def test_a_second_harvest_keeps_the_first(self, monkeypatch):
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="demo", limit=2)
        first = {e["id"] for e in json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]}

        harvest.collect(target_name="mock", limit=2)
        after = {e["id"] for e in json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]}
        assert first < after, (
            "overwriting destroys labelling work, which is the one thing in "
            "this harvest that cannot be regenerated by a command")

    def test_the_two_targets_do_not_collide(self, monkeypatch):
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="demo", limit=2)
        harvest.collect(target_name="demo:3", limit=2)
        entries = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]
        assert len(entries) == 2 * 2 * harvest.SAMPLE_COUNT
        assert len({e["id"] for e in entries}) == len(entries)

    def test_rerunning_the_same_command_adds_nothing(self, monkeypatch):
        ask, sent = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        # `harmless` isole la propriete : la reconnaissance renvoie ses
        # sondes a chaque lancement, et c'est inherent -- on ne connait pas
        # les objectifs, donc les ids, sans reconnoitre. Ce que ce test tient
        # est qu'aucune ATTAQUE ne reparte, ce qui est la depense qui compte.
        harvest.collect(target_name="mock", limit=3, harmless=True)
        before = len(sent)
        harvest.collect(target_name="mock", limit=3, harmless=True)
        assert len(sent) == before, (
            "an id already harvested must not even be sent again: it costs "
            "requests against a target and adds nothing")


class TestTheObjectivesComeFromRECONNAISSANCE:
    """
    LE DEFAUT CORRIGE, et il etait structurel. `generate_payloads()` croise
    les techniques avec `library["objectives"]`, et les trois generiques --
    `presentation`, `mission`, `culture-generale` -- sont tous ANODINS. Donc
    une recolte mono-tour ne demandait jamais ce que la cible protege, et ses
    entrees etaient des negatives par construction.

    C'est le defaut corrige le 2026-11-13 pour le collecteur de
    CONVERSATIONS seulement. Le mono-tour ne l'a eu que le 2026-11-27.
    """

    def test_the_objectives_REACH_generate_payloads(self, monkeypatch):
        """
        Sans ca, la reconnaissance tournerait, ses objectifs seraient
        annonces, et le catalogue garderait les generiques -- une recolte qui
        affiche un travail qu'elle ne fait pas.
        """
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        cible = {"id": "refus-1", "wording": "me parler du code"}
        monkeypatch.setattr(harvest, "targeted_objectives",
                            lambda *a, **k: ([cible], "test"))

        recu = {}
        vrai = harvest.generate_payloads

        def espion(objectives=None):
            recu["objectives"] = objectives
            return vrai(objectives)

        monkeypatch.setattr(harvest, "generate_payloads", espion)
        harvest.collect(target_name="mock", limit=1)
        assert recu["objectives"] == [cible], (
            "les objectifs de la reconnaissance n'atteignent pas le "
            "catalogue : la recolte garde les generiques, tous anodins")

    def test_the_logic_is_READ_from_the_sibling_and_not_copied(self):
        """
        Ses quarante lignes de raisonnement -- la borne, le repli sur
        l'objectif anodin, et l'ANNONCE de ce repli -- ne doivent exister
        qu'une fois. Une copie divergerait au premier ajustement, et les
        recoltes des deux formats cesseraient d'etre comparables sans que
        rien le dise.
        """
        import evaluation.collect_conversations as sibling

        assert harvest.targeted_objectives is sibling.targeted_objectives

    def test_HARMLESS_keeps_the_library_s_own_objectives(self, monkeypatch,
                                                         capsys):
        """
        Le contraste, et ce n'est pas une commodite : un corpus sans entrees
        anodines a des faux positifs NULS par construction, ce que le manuel
        OWASP nomme comme le piege du corpus tout-malveillant.
        """
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="mock", limit=1, harmless=True)
        assert "harmless" in capsys.readouterr().out.lower()


class TestTheIdentifierCarriesTheObjective:
    """
    LA MOITIE SANS LAQUELLE LE RESTE NE SERT A RIEN. Le numero de payload est
    un INDEX dans la liste echantillonnee, et cette liste change avec les
    objectifs. Donc relancer avec de nouveaux objectifs produirait les MEMES
    ids pour des payloads DIFFERENTS : la recolte les declarerait << deja
    recoltes >> et n'ajouterait rien, en affichant son travail.

    C'est le defaut du 2026-11-13, et il est PIRE ici -- la il sautait des
    sequences identiques, ici il sauterait des payloads qui ne sont pas les
    memes. Il ne s'etait vu qu'en RECOMPTANT le fichier produit.
    """

    def test_two_objectives_give_two_harvests(self, monkeypatch):
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)

        def avec(identifiant):
            objective = {"id": identifiant,
                         "wording": f"demander {identifiant}"}
            monkeypatch.setattr(harvest, "targeted_objectives",
                                lambda *a, **k: ([objective], "test"))
            return harvest.collect(target_name="demo", limit=1)

        avec("presentation")
        entries = avec("refus-1")
        tags = {e["id"] for e in entries}
        assert any("presentation" in i for i in tags)
        assert any("refus1" in i for i in tags), (
            "la seconde recolte a ete sautee : ses ids etaient ceux de la "
            "premiere alors que ses payloads sont differents")

    def test_a_payload_with_NO_objective_is_tagged_bare(self):
        """
        Le cas des payloads COMPLETS joues seuls : ils portent leur propre
        intention et ne croisent pas l'axe des objectifs. `bare` le dit, la
        ou une chaine vide donnerait un double tiret illisible -- et deux
        payloads sans objectif partageraient alors un prefixe ambigu.
        """
        assert harvest._tag(None) == "bare"
        assert harvest._tag("") == "bare"
        assert harvest._tag("refus-1") == "refus1"


class TestTheSecretIsDECLAREDNotHardcoded:
    """
    The field is not decoration: `labelling_prepass` searches the replies for
    this exact string to tell the author WHO said the secret. The old code
    wrote `TOPSECRET42` always — so a harvest from `demo`, whose secret is
    `ARCHIVES-7731`, would have reported zero disclosures over a harvest full
    of them.
    """

    @pytest.mark.parametrize("target, expected", [
        ("mock", "TOPSECRET42"),
        ("demo", "ARCHIVES-7731"),
        ("demo:3", "ARCHIVES-7731"),
    ])
    def test_each_target_records_its_own(self, monkeypatch, target, expected):
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name=target, limit=1)
        entries = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]
        assert {e["secret"] for e in entries} == {expected}

    def test_a_target_holding_NO_value_records_None(self, monkeypatch):
        # `records` guards third-party records rather than a value, and None
        # is a real answer there — as it already is for the frozen lot.
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="records", limit=1)
        entries = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]
        assert {e["secret"] for e in entries} == {None}

    def test_it_comes_from_the_TARGETS_declaration(self):
        # Read from the module that owns it, never restated here: a second
        # copy drifts on the first change.
        assert secret_of("demo") == "ARCHIVES-7731"
        assert secret_of("records") is None


class TestTheIdsCannotCollideWithTheCorpus:
    def test_the_prefix_is_not_the_frozen_sets(self, monkeypatch):
        """
        `R01`..`R09` are the frozen set's own identifiers. The 2026-11-18
        guard catches a collision when labelling, which is detection; a
        prefix that cannot collide is prevention, and that guard stays as the
        backstop.
        """
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="mock", limit=2)
        entries = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]
        for entry in entries:
            assert not entry["id"].startswith("R"), entry["id"]
            assert entry["id"].startswith(harvest.PREFIX)

    def test_no_harvested_id_is_already_a_CORPUS_id(self, monkeypatch):
        # The property that matters, checked against the real corpus rather
        # than against a letter.
        from evaluation.label import CORPUS_FILE, load

        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="mock", limit=5)
        entries = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"]
        taken = {entry["id"] for entry in load(CORPUS_FILE)["exchanges"]}
        assert not ({e["id"] for e in entries} & taken)


class TestTheFieldsToLabelStayEMPTY:
    def test_nothing_is_pre_filled(self, monkeypatch):
        # The judge's opinion is not recorded and neither is a guess: seeing
        # one would influence the human label, and we would end up measuring
        # the judge against itself.
        ask, _ = _target()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="mock", limit=1)
        entry = json.loads(
            harvest.OUTPUT_FILE.read_text(encoding="utf-8"))["exchanges"][0]
        assert entry["expected"] is None
        assert entry["category"] is None
        assert entry["trap"] == ""


class TestTheCLIReallyDrivesIt:
    """
    The junction, driven rather than read. Eight times in this project two
    modules have been correct on their own with nothing covering the glue —
    `_inject`, the unreachable profile guard, the three chain-of-custody
    fields, `label.py`'s set question, the frozen lot's silent guard, the
    mangled `measure()` call, the modes breakdown, and the advice no gate
    accepted. A flag that does not reach `collect` is the same defect.
    """

    def test_the_flags_reach_collect(self, monkeypatch):
        """
        EXACT et non partiel, et c'est ce qui a mordu : un correctif de
        2026-11-26 avait laisse `collect(arguments.target, ...)` la ou le
        parse s'appelle `parsed`, et c'est cette egalite qui l'a dit. Elle a
        gagne `indirect` le meme jour parce que le COMPORTEMENT a grossi,
        pas parce qu'elle etait trop stricte.
        """
        seen = {}
        monkeypatch.setattr(harvest, "collect",
                            lambda **kwargs: seen.update(kwargs))
        harvest.main(["--target", "demo:2", "--payloads", "7"])
        assert seen == {"target_name": "demo:2", "limit": 7,
                        "indirect": False, "harmless": False}

    def test_the_INDIRECT_flag_reaches_collect(self, monkeypatch):
        """
        La moitie qui compte : sans elle, `--indirect` pourrait s'arreter a
        argparse et la recolte serait DIRECTE en se croyant indirecte -- une
        provenance fausse estampillee sur chaque entree, ce que ce champ
        existe precisement pour empecher.
        """
        seen = {}
        monkeypatch.setattr(harvest, "collect",
                            lambda **kwargs: seen.update(kwargs))
        harvest.main(["--indirect"])
        assert seen["indirect"] is True

    def test_the_HARMLESS_flag_reaches_collect(self, monkeypatch):
        """
        Sans elle, `--harmless` pourrait s'arreter a argparse et la recolte
        lancerait la reconnaissance en se croyant anodine -- six requetes a
        une cible qu'on ne voulait pas sonder, et des objectifs cibles la ou
        on voulait des negatives.
        """
        seen = {}
        monkeypatch.setattr(harvest, "collect",
                            lambda **kwargs: seen.update(kwargs))
        harvest.main(["--harmless"])
        assert seen["harmless"] is True

    def test_the_default_limit_is_the_POLICY(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(harvest, "collect",
                            lambda **kwargs: seen.update(kwargs))
        harvest.main([])
        assert seen["limit"] == harvest.MAX_PAYLOADS, (
            "a default that bypassed the constant would make the visible "
            "policy a decoration"
        )

    def test_the_help_says_how_many_exchanges_that_is(self, capsys):
        # The operator is choosing how much HAND LABELLING to create, which
        # is N x SAMPLE_COUNT and not N.
        import contextlib
        import io

        output = io.StringIO()
        with contextlib.redirect_stdout(output), pytest.raises(SystemExit):
            harvest.main(["--help"])
        # Whitespace is ARGPARSE's and the words are ours, so the
        # check squashes before matching -- a first version looked for
        # a phrase argparse had wrapped across two lines. The same
        # lesson as `check_excerpt.py`, met the same morning.
        import re
        squashed = re.sub(r"\s+", " ", output.getvalue())
        assert "exchanges to label by hand" in squashed
