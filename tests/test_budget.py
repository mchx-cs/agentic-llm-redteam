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
from llm_client import (BudgetDepasse, demander_au_llm, journal,
                        reinitialiser_journal)
from rapport import construire, rendre_markdown


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

    monkeypatch.setattr(llm_client, "_client_pour", lambda profil: _Client())
    yield
    reinitialiser_journal()  # on ne laisse pas de plafond armé derrière soi


class TestPlafondAppels:
    def test_le_plafond_est_applique(self):
        reinitialiser_journal(max_appels=3)
        for _ in range(3):
            demander_au_llm("x")
        with pytest.raises(BudgetDepasse, match="3 appel"):
            demander_au_llm("x")

    def test_le_message_dit_le_compte_et_le_plafond(self):
        reinitialiser_journal(max_appels=1)
        demander_au_llm("x")
        with pytest.raises(BudgetDepasse, match="plafond 1"):
            demander_au_llm("x")


class TestPlafondTokens:
    def test_le_plafond_est_applique(self):
        # Chaque appel factice coûte 100 tokens.
        reinitialiser_journal(max_tokens=250)
        for _ in range(3):           # 300 tokens consommés
            demander_au_llm("x")
        with pytest.raises(BudgetDepasse, match="tokens"):
            demander_au_llm("x")

    def test_le_depassement_est_borne_a_un_appel(self):
        # Le coût d'un appel ne se connaît qu'après : on vérifie ce qui a
        # DÉJÀ été consommé, donc on peut dépasser d'un appel, jamais plus.
        reinitialiser_journal(max_tokens=250)
        for _ in range(3):
            demander_au_llm("x")
        assert journal()["tokens"] == 300
        with pytest.raises(BudgetDepasse):
            demander_au_llm("x")
        assert journal()["tokens"] == 300  # l'appel refusé n'a rien coûté


class TestSansPlafond:
    def test_par_defaut_rien_n_est_limite(self):
        # Les scripts d'évaluation consomment bien plus qu'une campagne et
        # n'ont aucune raison d'être coupés au milieu d'une mesure.
        reinitialiser_journal()
        for _ in range(50):
            demander_au_llm("x")
        assert journal()["appels"] == 50

    def test_la_remise_a_zero_desarme_le_plafond(self):
        reinitialiser_journal(max_appels=1)
        demander_au_llm("x")
        reinitialiser_journal()
        demander_au_llm("x")          # ne doit plus lever
        assert journal()["appels"] == 1


class TestArretPropre:
    def test_le_budget_n_est_pas_une_panne(self):
        # Distinguer les deux permet à l'orchestrateur de conclure
        # « écourtée » au lieu de « plantée ».
        assert issubclass(BudgetDepasse, RuntimeError)

    def test_le_rapport_annonce_une_campagne_ecourtee(self):
        resultat = {
            "statut": "budget_epuise", "fiche": None,
            "plan": {"essais": [{"technique": "t", "famille_owasp": "LLM01",
                                 "objectif": "o", "transformation": "identite",
                                 "texte": "p"}], "ecartees": []},
            "constats": [], "ecourtee": "Budget atteint : 6 appel(s).",
            "journal": {"appels": 6, "tokens": 100, "tronquees": []},
        }
        texte = rendre_markdown(construire(resultat, cible="essai"))
        assert "ÉCOURTÉE" in texte
        # Et surtout : la couverture doit se dénoncer elle-même.
        assert "incomplète" in texte

    def test_une_campagne_complete_ne_porte_aucun_avertissement(self):
        resultat = {
            "statut": "aucun_constat", "fiche": None,
            "plan": {"essais": [], "ecartees": []}, "constats": [],
            "ecourtee": None, "journal": {},
        }
        texte = rendre_markdown(construire(resultat, cible="essai"))
        assert "ÉCOURTÉE" not in texte
