"""
Tests for the labelling tool — the one file in `evaluation/` that had none.

Why it had none: `evaluation/` holds the measurements that NEED a model, and
`tests/` must never call one. But `etiqueter.py` calls no model at all. It
reads two JSON working files, asks the author questions, and writes a corpus.
Its interactive half cannot be tested without faking a terminal; its
INTEGRATION half can, and that is the half that touches the ground truth.

The gap cost a real defect, found by reading the file rather than by running
it: `integrate()` ended on `restants`, a local of `label()`, so the command
raised a NameError on its very last line — after having written the corpus.
The data survived, the closing message did not, and nothing reported it.
"""

import json

import pytest

from evaluation import etiqueter


def _entry(identifier, group, expected=True, dataset="dev"):
    return {"id": identifier, "groupe": group, "categorie": "controle",
            "jeu": dataset, "secret": "TOPSECRET42", "source": "essai",
            "payload": "p", "reponse": "r", "attendu": expected,
            "piege": "x"}


@pytest.fixture
def harvests(tmp_path, monkeypatch):
    """Two working files and an empty corpus, all inside tmp_path."""
    to_label = tmp_path / "a_etiqueter.json"
    conversations = tmp_path / "a_etiqueter_conversations.json"
    corpus = tmp_path / "echanges_etiquetes.json"
    corpus.write_text(json.dumps({"echanges": []}), encoding="utf-8")

    monkeypatch.setattr(etiqueter, "TO_LABEL_FILE", to_label)
    monkeypatch.setattr(etiqueter, "CONVERSATIONS_FILE", conversations)
    monkeypatch.setattr(etiqueter, "CORPUS_FILE", corpus)
    monkeypatch.setattr(etiqueter, "SOURCES",
                        ((to_label, "echanges"),
                         (conversations, "conversations")))
    return {"a_etiqueter": to_label, "conversations": conversations,
            "corpus": corpus}


class TestIntegration:
    def test_un_echange_etiquete_rejoint_le_corpus(self, harvests, capsys):
        harvests["a_etiqueter"].write_text(
            json.dumps({"echanges": [_entry("R01-1", "R01")]}),
            encoding="utf-8")
        etiqueter.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert [e["id"] for e in corpus["echanges"]] == ["R01-1"]
        # Et la récolte ne garde que ce qui reste à étiqueter : ici rien.
        reste = json.loads(harvests["a_etiqueter"].read_text(encoding="utf-8"))
        assert reste["echanges"] == []

    def test_integrer_va_jusqu_au_bout(self, harvests, capsys):
        """
        LE test qui manquait. `integrate()` doit RENDRE, pas lever : la
        dernière ligne nommait une variable d'une autre fonction, et le
        corpus était écrit avant que ça casse. Un défaut muet pour les
        données, bruyant pour l'opérateur, et couvert par rien.
        """
        harvests["a_etiqueter"].write_text(
            json.dumps({"echanges": [_entry("R01-1", "R01"),
                                     _entry("R02-1", "R02", expected=None)]}),
            encoding="utf-8")
        etiqueter.integrate()                      # ne doit pas lever
        sortie = capsys.readouterr().out
        assert "1 échange(s) ajouté(s)" in sortie
        # Et le compte de ce qui reste est JUSTE : l'entrée non étiquetée.
        assert "1 échange(s) restent à étiqueter" in sortie

    def test_rien_a_integrer_ne_touche_pas_le_corpus(self, harvests):
        harvests["a_etiqueter"].write_text(
            json.dumps({"echanges": [_entry("R01-1", "R01", expected=None)]}),
            encoding="utf-8")
        etiqueter.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert corpus["echanges"] == []

    def test_un_groupe_ne_se_repartit_pas_entre_les_jeux(self, harvests,
                                                        capsys):
        """
        Le garde-fou qui compte : le jeu gelé ne doit jamais recevoir la
        reformulation d'un cas sur lequel l'arbitre a été réglé.
        """
        harvests["corpus"].write_text(
            json.dumps({"echanges": [_entry("R01-1", "R01", dataset="dev")]}),
            encoding="utf-8")
        harvests["a_etiqueter"].write_text(
            json.dumps({"echanges": [_entry("R01-2", "R01", dataset="test")]}),
            encoding="utf-8")
        etiqueter.integrate()
        corpus = json.loads(harvests["corpus"].read_text(encoding="utf-8"))
        assert [e["id"] for e in corpus["echanges"]] == ["R01-1"]
        assert "Ignoré" in capsys.readouterr().out

    def test_une_conversation_est_signalee_comme_non_mesuree(self, harvests,
                                                             capsys):
        """
        Un corpus qui grandit sans que la mesure change doit s'expliquer.
        """
        conversation = _entry("C-01-1", "C-01")
        conversation["tours"] = [{"role": "utilisateur", "contenu": "a"},
                                 {"role": "cible", "contenu": "b"}]
        harvests["conversations"].write_text(
            json.dumps({"conversations": [conversation]}), encoding="utf-8")
        etiqueter.integrate()
        assert "ne sont PAS encore mesurées" in capsys.readouterr().out


class TestCeQuiResteAEtiqueter:
    def test_il_compte_les_deux_recoltes(self, harvests):
        harvests["a_etiqueter"].write_text(
            json.dumps({"echanges": [_entry("R01-1", "R01", expected=None)]}),
            encoding="utf-8")
        harvests["conversations"].write_text(
            json.dumps({"conversations": [
                _entry("C-01-1", "C-01", expected=None)]}),
            encoding="utf-8")
        assert etiqueter._left_to_label(etiqueter._harvests()) == 2

    def test_une_recolte_absente_n_est_pas_une_erreur(self, harvests):
        assert etiqueter._harvests() == []
        assert etiqueter._left_to_label([]) == 0
