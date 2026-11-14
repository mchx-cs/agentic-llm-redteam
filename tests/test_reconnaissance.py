"""
Tests for reconnaissance, with no call to a model at all.

We do not test the QUALITY of the profile here — that is the job of
`evaluation/tester_reconnaissance.py`, which needs a real model and simulated
targets. We test what must be true whatever a model answers: the profile's
normalisation, and above all the two TRI-STATES added on 2026-11-11.

Why they deserve tests of their own: `produit_du_code` and
`traite_des_documents` are True, False or None, and the difference between
False ("the target says it cannot") and None ("it said nothing about it")
decides whether nine to sixteen probes are skipped. A `bool()` dropped in by
accident would turn every silence into a refusal, and the campaign would lose
whole families — without raising the slightest exception.
"""

import pytest

import agents.reconnaissance as reconnaissance
from agents.reconnaissance import (KNOWN_CONTEXTS, PROBES, reconnoitre,
                                   summarise)

CHAMPS_ATTENDUS = {"role", "langue", "outils", "sujets_refuses",
                   "mentionne_consignes", "produit_du_code",
                   "traite_des_documents", "contexte", "indices", "echanges",
                   "avertissement"}


@pytest.fixture
def analyst(monkeypatch):
    """Remplace l'appel au modèle d'analyse par une sortie choisie."""
    def installer(sortie):
        monkeypatch.setattr(reconnaissance, "ask_llm",
                            lambda *a, **k: sortie)
    return installer


def _target(reply="une réponse"):
    return lambda message: reply


class TestProfileShape:
    def test_every_field_is_present(self, analyst):
        analyst('{"role": "assistant", "langue": "fr"}')
        assert set(reconnoitre(_target())) == CHAMPS_ATTENDUS

    def test_an_unreadable_analysis_gives_an_empty_profile_not_an_invented_one(
            self, analyst):
        # An incomplete profile is useful, an invented one is harmful.
        analyst("ceci n'est pas du JSON")
        profile = reconnoitre(_target())
        assert set(profile) == CHAMPS_ATTENDUS
        assert profile["avertissement"]
        assert profile["role"] is None
        assert profile["outils"] == []

    def test_an_empty_profile_keeps_the_exchanges(self, analyst):
        # Without them, there is no way to understand why the analysis
        # failed.
        analyst("pas du JSON")
        assert len(reconnoitre(_target())["echanges"]) == len(PROBES)

    def test_the_types_are_enforced(self, analyst):
        # Un champ du mauvais type deviendrait une erreur beaucoup plus loin,
        # dans le planificateur.
        analyst('{"role": 42, "outils": "pas une liste", '
                 '"sujets_refuses": [1, "vrai sujet"], "indices": null}')
        profile = reconnoitre(_target())
        assert profile["role"] is None
        assert profile["outils"] == []
        assert profile["sujets_refuses"] == ["vrai sujet"]
        assert profile["indices"] == []


class TestTriStates:
    """
    The False / None distinction decides whether `packagehallucination`
    (7 probes) and `latentinjection` (9 probes) are skipped.
    """

    @pytest.mark.parametrize("field", ["produit_du_code",
                                       "traite_des_documents"])
    @pytest.mark.parametrize("valeur, attendu", [
        ("true", True),
        ("false", False),
        ("null", None),
    ])
    def test_the_three_states_survive(self, analyst, field, valeur,
                                       attendu):
        analyst('{"%s": %s}' % (field, valeur))
        assert reconnoitre(_target())[field] is attendu

    @pytest.mark.parametrize("field", ["produit_du_code",
                                       "traite_des_documents"])
    def test_a_missing_field_means_none_not_false(self, analyst, field):
        # THE trap: `bool()` or `.get(field, False)` would turn every
        # silence into a refusal, and the campaign would lose sixteen probes.
        analyst('{"role": "assistant"}')
        assert reconnoitre(_target())[field] is None

    @pytest.mark.parametrize("field", ["produit_du_code",
                                       "traite_des_documents"])
    def test_a_non_boolean_value_means_none(self, analyst, field):
        # A model can answer "oui" instead of true: we do not guess, we fall
        # back on "not declared".
        analyst('{"%s": "oui"}' % field)
        assert reconnoitre(_target())[field] is None

    def test_an_empty_profile_sets_them_to_none(self, analyst):
        analyst("illisible")
        profile = reconnoitre(_target())
        assert profile["produit_du_code"] is None
        assert profile["traite_des_documents"] is None


class TestDeclaredContext:
    """
    The context comes from the OPERATOR, never from a probe: a target does not
    know what its output is rendered in, and asking it would invite
    hallucination.
    """

    def test_reconnaissance_never_fills_it(self, analyst):
        # Even if the analyst model claims to know it.
        analyst('{"contexte": ["terminal", "rendu-riche"]}')
        assert reconnoitre(_target())["contexte"] == []

    def test_no_probe_asks_about_the_context(self):
        # Garde-fou contre la tentation : si quelqu'un ajoute « ta sortie est
        # rendue en Markdown ? » aux sondes, ce test tombe.
        questions = " ".join(PROBES).lower()
        for interdit in ("markdown", "html", "terminal", "rendu"):
            assert interdit not in questions, interdit

    def test_the_context_names_are_documented(self):
        # Ils apparaissent dans le message d'erreur de la ligne de commande :
        # un nom sans explication ne guiderait personne.
        assert KNOWN_CONTEXTS
        for nom, explication in KNOWN_CONTEXTS.items():
            assert nom == nom.lower()
            assert explication.strip()


class TestBudgetAndDisplay:
    def test_the_probing_loop_is_bounded(self, monkeypatch, analyst):
        # Toute boucle a sa limite : ici RECON_BUDGET, distinct de
        # MAX_ESSAIS, because probing can already wake the defences.
        monkeypatch.setattr(reconnaissance, "RECON_BUDGET", 2)
        analyst("{}")
        assert len(reconnoitre(_target())["echanges"]) == 2

    def test_every_probe_targets_one_field(self):
        # A recorded principle: one probe fewer must mean one fact fewer,
        # never a false profile. Hence one probe per probed field.
        assert len(PROBES) == len(
            {"role", "capacites", "sujets_refuses", "outils",
             "produit_du_code", "traite_des_documents"})

    def test_the_summary_shows_the_new_fields(self, analyst):
        analyst('{"produit_du_code": true, "traite_des_documents": false}')
        rendu = summarise(reconnoitre(_target()))
        assert "écrit du code : oui" in rendu
        assert "lit des documents : non" in rendu
        assert "contexte déclaré : aucun" in rendu

    def test_the_summary_tells_no_from_not_declared(self, analyst):
        analyst('{"produit_du_code": null}')
        assert "écrit du code : non déclaré" in summarise(reconnoitre(_target()))
