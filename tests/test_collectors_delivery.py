"""
Les deux collecteurs estampillent la PROVENANCE, et un seul peut récolter de
l'indirect.

Aucun appel à un modèle. Ce qui est tenu ici est le maillon que l'entrée du
2026-11-26 avait nommé comme non fait : `label.py` CONSERVE un `delivery` déjà
posé, donc la chaîne était prête côté corpus et il manquait que la source le
pose.
"""

import json
import pathlib

import pytest

import evaluation.collect_conversations as conversations
import evaluation.collect_exchanges as harvest
from targets.indirect import INDIRECT_TRIGGER, NoIndirectChannel


class _Direct:
    """Une cible sans canal indirect : le cas par défaut."""

    conversation = False

    def __init__(self):
        self.asked = []

    def __call__(self, message, history=None):
        self.asked.append(message)
        return "reponse"


class _Plantable(_Direct):
    """Une cible qui DÉCLARE le canal, comme `docs`."""

    indirect = True

    def __init__(self):
        super().__init__()
        self.planted = []

    def plant(self, text):
        self.planted.append(text)


@pytest.fixture
def harvest_file(monkeypatch, tmp_path):
    monkeypatch.setattr(harvest, "OUTPUT_FILE", tmp_path / "to_label.json")
    monkeypatch.setattr(harvest, "GARAK_FILE", tmp_path / "absent.json",
                        raising=False)
    return tmp_path / "to_label.json"


def _entries(path):
    return json.loads(path.read_text(encoding="utf-8"))["exchanges"]


class TestTheChannelIsREQUIREDAndNeverGuessed:
    """
    Une cible qui jette la note en silence laisserait croire qu'on a mené une
    attaque indirecte quand le modèle n'a jamais vu la note : le juge noterait
    un échange anodin et la récolte porterait une provenance FAUSSE. C'est la
    famille du gabarit sans `{message}`, de la capability de conversation
    devinée et des trois champs de chaîne de possession — un défaut qui ne
    lève pas et qui INVERSE la conclusion.
    """

    def test_a_target_without_the_channel_is_REFUSED(self, monkeypatch,
                                                     harvest_file):
        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Direct())
        with pytest.raises(NoIndirectChannel):
            harvest.collect(target_name="mock", limit=1, indirect=True)

    def test_the_refusal_comes_out_as_an_INSTRUCTION_and_not_a_traceback(
            self, monkeypatch, harvest_file, capsys):
        """
        Un traceback sur une erreur légitime d'opérateur est le défaut
        corrigé pour les campagnes — « huit lignes de traceback avec le bon
        message noyé dedans ». Le message de `require_indirect` dit déjà quoi
        faire ; il ne lui manquait que de sortir seul, avec un code.
        """
        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Direct())
        assert harvest.main(["--target", "mock", "--indirect"]) == 2
        err = capsys.readouterr().err
        assert "REFUSED" in err
        assert "docs" in err, (
            "le refus doit nommer la cible qui a le canal, sinon il dit "
            "seulement non")

    def test_the_DIRECT_path_needs_no_channel(self, monkeypatch,
                                              harvest_file):
        # Le contraste : sans lui, un garde qui refuse tout passerait.
        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Direct())
        harvest.collect(target_name="mock", limit=1)
        assert _entries(harvest_file)


class TestWhatTheIndirectHarvestActuallySends:

    def test_the_payload_is_PLANTED_and_the_TRIGGER_is_asked(
            self, monkeypatch, harvest_file):
        """
        LE CŒUR DU MODE. Si le payload était envoyé comme message, la récolte
        serait DIRECTE en s'estampillant indirecte — et toutes les entrées
        porteraient une provenance fausse.
        """
        ask = _Plantable()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="docs", limit=1, indirect=True)

        assert ask.planted, "rien n'a été planté"
        assert set(ask.asked) == {INDIRECT_TRIGGER}, (
            f"la cible a reçu autre chose que le déclencheur : {ask.asked}")
        assert all(p not in ask.asked for p in ask.planted)

    def test_the_trigger_is_READ_from_the_contract_and_not_restated(self):
        """
        Il vit dans `targets/indirect.py`, qui DÉCLARE le canal — la
        préférence déjà enregistrée pour `stats.STATES` et
        `split_sets.imposed_set()`. Une copie dans le collecteur divergerait
        de celle de l'orchestrateur, et les deux récoltes cesseraient d'être
        comparables sans que rien le dise.
        """
        import main

        assert harvest.INDIRECT_TRIGGER is INDIRECT_TRIGGER
        assert main.INDIRECT_TRIGGER is INDIRECT_TRIGGER

    def test_the_trigger_asks_for_NOTHING_sensitive(self):
        """
        Il doit rester anodin : c'est ce qui rend le registre scorable. Si le
        déclencheur demandait le secret, l'échange que le juge voit porterait
        une partie de l'attaque et le résultat ne dirait plus rien de la
        note.
        """
        low = INDIRECT_TRIGGER.lower()
        for word in ("code", "secret", "consigne", "instruction", "mot de "
                     "passe", "ignore"):
            assert word not in low


class TestTheEntryCarriesItsProvenance:

    def test_an_indirect_entry_is_stamped_and_keeps_what_was_PLANTED(
            self, monkeypatch, harvest_file):
        ask = _Plantable()
        monkeypatch.setattr(harvest, "choose_target", lambda name=None: ask)
        harvest.collect(target_name="docs", limit=1, indirect=True)

        for entry in _entries(harvest_file):
            assert entry["delivery"] == "indirect"
            assert entry["planted"], (
                "sans le texte planté, l'entrée ne dit pas ce que la cible a "
                "lu — et le juge, qui ne le voit pas, ne pourra jamais le "
                "reconstituer")
            assert entry["payload"] == INDIRECT_TRIGGER, (
                "`payload` doit porter ce qui a été DEMANDÉ : c'est "
                "l'échange que le juge verra, et en indirect les deux "
                "diffèrent")

    def test_a_direct_entry_is_stamped_direct(self, monkeypatch,
                                              harvest_file):
        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Direct())
        harvest.collect(target_name="mock", limit=1)
        for entry in _entries(harvest_file):
            assert entry["delivery"] == "direct"
            assert entry["planted"] is None

    def test_the_two_deliveries_do_not_COLLIDE_on_their_ids(
            self, monkeypatch, harvest_file):
        """
        LA RÉCOLTE SAUTE LES IDS DÉJÀ PRÉSENTS. Une récolte indirecte qui
        réutiliserait les ids directs serait donc déclarée « déjà récoltée »
        et n'ajouterait RIEN, en affichant son travail — le défaut exact du
        2026-11-13, où quatre séquences sur huit n'ont jamais reçu leur
        nouvel objectif, et qui ne s'est vu qu'en RECOMPTANT le fichier.
        """
        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Direct())
        harvest.collect(target_name="docs", limit=1)
        direct = {e["id"] for e in _entries(harvest_file)}

        monkeypatch.setattr(harvest, "choose_target",
                            lambda name=None: _Plantable())
        harvest.collect(target_name="docs", limit=1, indirect=True)
        both = _entries(harvest_file)
        indirect = {e["id"] for e in both if e["delivery"] == "indirect"}

        assert indirect, "la récolte indirecte n'a rien ajouté"
        assert not (direct & indirect)
        assert len(both) == len(direct) + len(indirect)


class TestTheConversationCollectorHasNoIndirectMode:
    """
    ET C'EST UNE DÉCISION DU PROJET, pas un oubli. `main.py` refuse
    `--indirect` avec `--multiturn` depuis le 2026-11-25, avec sa raison :
    une attaque indirecte multi-tours n'a jamais été mesurée ici et le pont
    PyRIT ne sait rien de la note plantée.

    Lui donner ce mode ferait entrer dans le corpus des entrées d'une forme
    que la CAMPAGNE ne peut pas produire — et un corpus qui contient ce que
    l'outil ne sait pas faire ne mesure plus l'outil.
    """

    def test_its_entries_are_stamped_direct(self):
        entry = conversations._entry(
            "G", 1, {"technique": "t", "objective": "o"},
            [{"role": "attacker", "content": "q"},
             {"role": "chatbot", "content": "r"}])
        assert entry["delivery"] == "direct"

    def test_it_offers_NO_indirect_flag(self, capsys):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with pytest.raises(SystemExit):
                conversations.main(["--help"])
        assert "--indirect" not in out.getvalue(), (
            "un mode indirect ici contredirait la garde de l'orchestrateur, "
            "qui refuse les deux livraisons ensemble")

    def test_the_orchestrator_still_refuses_both_deliveries(self):
        """
        La garde dont celle-ci hérite sa raison. Si elle disparaissait, la
        décision de ne pas donner ce mode au collecteur perdrait son
        fondement — et ce test le dirait plutôt que de la laisser orpheline.
        """
        source = pathlib.Path("main.py").read_text(encoding="utf-8")
        assert "arguments.indirect and arguments.multiturn" in source
        assert "two DELIVERIES" in source

    def test_the_single_turn_collector_CAN_do_it(self):
        """
        Le contraste qui fait que le test précédent dit quelque chose : ce
        n'est pas « aucun collecteur ne sait récolter de l'indirect », c'est
        « celui-là ne peut pas, et l'autre oui ».
        """
        import inspect

        assert "indirect" in inspect.signature(harvest.collect).parameters
