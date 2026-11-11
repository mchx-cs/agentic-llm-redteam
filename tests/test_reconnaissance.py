"""
Tests de la reconnaissance, sans aucun appel à un modèle.

On ne teste pas ici la QUALITÉ de la fiche — ça, c'est le travail de
`evaluation/tester_reconnaissance.py`, qui a besoin d'un vrai modèle et de
cibles simulées. On teste ce qui doit être vrai quoi qu'un modèle réponde : la
normalisation de la fiche, et surtout les deux TRI-ÉTATS ajoutés le
2026-11-11.

Pourquoi ils méritent leurs propres tests : `produit_du_code` et
`traite_des_documents` valent True, False ou None, et la différence entre
False (« la cible dit ne pas savoir ») et None (« elle n'en a rien dit »)
décide d'écarter ou non neuf à seize sondes. Un `bool()` posé par mégarde
transformerait tous les silences en refus, et la campagne perdrait des
familles entières — sans lever la moindre exception.
"""

import pytest

import agents.reconnaissance as reconnaissance
from agents.reconnaissance import (CONTEXTES_CONNUS, SONDES, reconnaitre,
                                   resumer)

CHAMPS_ATTENDUS = {"role", "langue", "outils", "sujets_refuses",
                   "mentionne_consignes", "produit_du_code",
                   "traite_des_documents", "contexte", "indices", "echanges",
                   "avertissement"}


@pytest.fixture
def analyser(monkeypatch):
    """Remplace l'appel au modèle d'analyse par une sortie choisie."""
    def installer(sortie):
        monkeypatch.setattr(reconnaissance, "demander_au_llm",
                            lambda *a, **k: sortie)
    return installer


def _cible(reponse="une réponse"):
    return lambda message: reponse


class TestFormeDeLaFiche:
    def test_tous_les_champs_sont_presents(self, analyser):
        analyser('{"role": "assistant", "langue": "fr"}')
        assert set(reconnaitre(_cible())) == CHAMPS_ATTENDUS

    def test_une_analyse_illisible_donne_une_fiche_vide_pas_inventee(
            self, analyser):
        # Une fiche incomplète est utile, une fiche inventée est nuisible.
        analyser("ceci n'est pas du JSON")
        fiche = reconnaitre(_cible())
        assert set(fiche) == CHAMPS_ATTENDUS
        assert fiche["avertissement"]
        assert fiche["role"] is None
        assert fiche["outils"] == []

    def test_une_fiche_vide_garde_les_echanges(self, analyser):
        # Sans eux, impossible de comprendre pourquoi l'analyse a échoué.
        analyser("pas du JSON")
        assert len(reconnaitre(_cible())["echanges"]) == len(SONDES)

    def test_les_types_sont_imposes(self, analyser):
        # Un champ du mauvais type deviendrait une erreur beaucoup plus loin,
        # dans le planificateur.
        analyser('{"role": 42, "outils": "pas une liste", '
                 '"sujets_refuses": [1, "vrai sujet"], "indices": null}')
        fiche = reconnaitre(_cible())
        assert fiche["role"] is None
        assert fiche["outils"] == []
        assert fiche["sujets_refuses"] == ["vrai sujet"]
        assert fiche["indices"] == []


class TestTriEtats:
    """
    La distinction False / None décide d'écarter ou non `packagehallucination`
    (7 sondes) et `latentinjection` (9 sondes).
    """

    @pytest.mark.parametrize("champ", ["produit_du_code",
                                       "traite_des_documents"])
    @pytest.mark.parametrize("valeur, attendu", [
        ("true", True),
        ("false", False),
        ("null", None),
    ])
    def test_les_trois_etats_survivent(self, analyser, champ, valeur,
                                       attendu):
        analyser('{"%s": %s}' % (champ, valeur))
        assert reconnaitre(_cible())[champ] is attendu

    @pytest.mark.parametrize("champ", ["produit_du_code",
                                       "traite_des_documents"])
    def test_un_champ_absent_vaut_none_pas_false(self, analyser, champ):
        # C'est LE piège : `bool()` ou `.get(champ, False)` transformerait
        # tous les silences en refus, et la campagne perdrait seize sondes.
        analyser('{"role": "assistant"}')
        assert reconnaitre(_cible())[champ] is None

    @pytest.mark.parametrize("champ", ["produit_du_code",
                                       "traite_des_documents"])
    def test_une_valeur_non_booleenne_vaut_none(self, analyser, champ):
        # Un modèle peut répondre "oui" au lieu de true : on ne devine pas,
        # on retombe sur « non déclaré ».
        analyser('{"%s": "oui"}' % champ)
        assert reconnaitre(_cible())[champ] is None

    def test_une_fiche_vide_les_met_a_none(self, analyser):
        analyser("illisible")
        fiche = reconnaitre(_cible())
        assert fiche["produit_du_code"] is None
        assert fiche["traite_des_documents"] is None


class TestContexteDeclare:
    """
    Le contexte vient de l'OPÉRATEUR, jamais d'une sonde : une cible ne sait
    pas dans quoi sa sortie est rendue, et le lui demander inviterait à
    l'hallucination.
    """

    def test_la_reconnaissance_ne_le_remplit_jamais(self, analyser):
        # Même si le modèle d'analyse prétend le connaître.
        analyser('{"contexte": ["terminal", "rendu-riche"]}')
        assert reconnaitre(_cible())["contexte"] == []

    def test_aucune_sonde_ne_demande_le_contexte(self):
        # Garde-fou contre la tentation : si quelqu'un ajoute « ta sortie est
        # rendue en Markdown ? » aux sondes, ce test tombe.
        questions = " ".join(SONDES).lower()
        for interdit in ("markdown", "html", "terminal", "rendu"):
            assert interdit not in questions, interdit

    def test_les_noms_de_contexte_sont_documentes(self):
        # Ils apparaissent dans le message d'erreur de la ligne de commande :
        # un nom sans explication ne guiderait personne.
        assert CONTEXTES_CONNUS
        for nom, explication in CONTEXTES_CONNUS.items():
            assert nom == nom.lower()
            assert explication.strip()


class TestBudgetEtAffichage:
    def test_la_boucle_de_sondage_est_bornee(self, monkeypatch, analyser):
        # Toute boucle a sa limite : ici BUDGET_RECONNAISSANCE, distinct de
        # MAX_ESSAIS parce que sonder peut déjà éveiller les défenses.
        monkeypatch.setattr(reconnaissance, "BUDGET_RECONNAISSANCE", 2)
        analyser("{}")
        assert len(reconnaitre(_cible())["echanges"]) == 2

    def test_chaque_sonde_vise_un_champ(self):
        # Principe consigné : une sonde en moins doit être une information en
        # moins, jamais une fiche fausse. Donc une sonde par champ sondé.
        assert len(SONDES) == len(
            {"role", "capacites", "sujets_refuses", "outils",
             "produit_du_code", "traite_des_documents"})

    def test_le_resume_affiche_les_nouveaux_champs(self, analyser):
        analyser('{"produit_du_code": true, "traite_des_documents": false}')
        rendu = resumer(reconnaitre(_cible()))
        assert "écrit du code : oui" in rendu
        assert "lit des documents : non" in rendu
        assert "contexte déclaré : aucun" in rendu

    def test_le_resume_distingue_non_de_non_declare(self, analyser):
        analyser('{"produit_du_code": null}')
        assert "écrit du code : non déclaré" in resumer(reconnaitre(_cible()))
