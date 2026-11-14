"""
Tests du budget de campagne.

Le budget est un COUPE-CIRCUIT, pas une économie : à l'échelle actuelle une
campagne coûte des centimes. Ce qu'il arrête, c'est la boucle qui s'emballe.

Deux propriétés comptent, et la seconde plus que la première :
1. le plafond est réellement appliqué ;
2. l'arrêt est PROPRE — une campagne écourtée ne doit jamais se présenter
   comme une campagne terminée, sans quoi « aucun constat » laisserait croire
   à une couverture qui n'a pas eu lieu.
"""

import pytest

import llm_client
from llm_client import (BudgetExceeded, ask_llm, call_log,
                        reset_call_log)
from rapport import build_report, render_markdown


@pytest.fixture(autouse=True)
def modele_factice(monkeypatch):
    """Un modèle qui répond instantanément, sans réseau ni quota."""
    class _Usage:
        total_tokens = 100

    class _Choix:
        finish_reason = "stop"
        message = type("M", (), {"content": "réponse"})()

    class _Reponse:
        usage = _Usage()
        choices = [_Choix()]

    class _Client:
        chat = type("C", (), {"completions": type("D", (), {
            "create": staticmethod(lambda **k: _Reponse())})()})()

    monkeypatch.setattr(llm_client, "_client_for", lambda profil: _Client())
    yield
    reset_call_log()  # on ne laisse pas de plafond armé derrière soi


class TestPlafondAppels:
    def test_le_plafond_est_applique(self):
        reset_call_log(max_calls=3)
        for _ in range(3):
            ask_llm("x")
        with pytest.raises(BudgetExceeded, match="3 appel"):
            ask_llm("x")

    def test_le_message_dit_le_compte_et_le_plafond(self):
        reset_call_log(max_calls=1)
        ask_llm("x")
        with pytest.raises(BudgetExceeded, match="plafond 1"):
            ask_llm("x")


class TestPlafondTokens:
    def test_le_plafond_est_applique(self):
        # Chaque appel factice coûte 100 tokens.
        reset_call_log(max_tokens=250)
        for _ in range(3):           # 300 tokens consommés
            ask_llm("x")
        with pytest.raises(BudgetExceeded, match="tokens"):
            ask_llm("x")

    def test_le_depassement_est_borne_a_un_appel(self):
        # Le coût d'un appel ne se connaît qu'après : on vérifie ce qui a
        # DÉJÀ été consommé, donc on peut dépasser d'un appel, jamais plus.
        reset_call_log(max_tokens=250)
        for _ in range(3):
            ask_llm("x")
        assert call_log()["tokens"] == 300
        with pytest.raises(BudgetExceeded):
            ask_llm("x")
        assert call_log()["tokens"] == 300  # l'appel refusé n'a rien coûté


class TestSansPlafond:
    def test_par_defaut_rien_n_est_limite(self):
        # Les scripts d'évaluation consomment bien plus qu'une campagne et
        # n'ont aucune raison d'être coupés au milieu d'une mesure.
        reset_call_log()
        for _ in range(50):
            ask_llm("x")
        assert call_log()["appels"] == 50

    def test_la_remise_a_zero_desarme_le_plafond(self):
        reset_call_log(max_calls=1)
        ask_llm("x")
        reset_call_log()
        ask_llm("x")          # ne doit plus lever
        assert call_log()["appels"] == 1


class TestArretPropre:
    def test_le_budget_n_est_pas_une_panne(self):
        # Distinguer les deux permet à l'orchestrateur de conclure
        # « écourtée » au lieu de « plantée ».
        assert issubclass(BudgetExceeded, RuntimeError)

    def test_le_rapport_annonce_une_campagne_ecourtee(self):
        resultat = {
            "statut": "budget_epuise", "fiche": None,
            "plan": {"essais": [{"technique": "t", "famille_owasp": "LLM01",
                                 "objectif": "o", "transformation": "identite",
                                 "texte": "p"}], "ecartees": []},
            "constats": [], "ecourtee": "Budget atteint : 6 appel(s).",
            "journal": {"appels": 6, "tokens": 100, "tronquees": []},
        }
        texte = render_markdown(build_report(resultat, target="essai"))
        assert "ÉCOURTÉE" in texte
        # Et surtout : la couverture doit se dénoncer elle-même.
        assert "incomplète" in texte

    def test_une_campagne_complete_ne_porte_aucun_avertissement(self):
        resultat = {
            "statut": "aucun_constat", "fiche": None,
            "plan": {"essais": [], "ecartees": []}, "constats": [],
            "ecourtee": None, "journal": {},
        }
        texte = render_markdown(build_report(resultat, target="essai"))
        assert "ÉCOURTÉE" not in texte
