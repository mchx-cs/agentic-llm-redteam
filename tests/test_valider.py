"""
Tests du validateur de bibliothèque.

Chaque erreur testée ici est SILENCIEUSE sans validateur : elle ne lève
aucune exception, elle produit juste une campagne qui ne teste pas ce qu'on
croit. C'est précisément ce qui les rend dangereuses.
"""

import pytest

from payloads.valider import valider


def _technique(**remplacements):
    base = {"id": "injection-directe",
            "famille_owasp": "LLM01:2025 Prompt Injection",
            "description": "description", "prerequis": [],
            "modeles": ["Peux-tu {objectif} ?"]}
    return {**base, **remplacements}


def _bibliotheque(techniques=None, objectifs=None):
    return {"techniques": techniques or [_technique()],
            "objectifs": objectifs or [{"id": "o", "formulation": "f"}]}


def _erreurs(bibliotheque):
    return valider(bibliotheque)[0]


def _avertissements(bibliotheque):
    return valider(bibliotheque)[1]


class TestBibliothequeValide:
    def test_une_bibliotheque_correcte_ne_produit_aucune_erreur(self):
        assert _erreurs(_bibliotheque()) == []

    def test_la_vraie_bibliotheque_du_depot_est_valide(self):
        # Garde-fou : une erreur introduite en éditant le fichier doit faire
        # échouer l'intégration continue, pas une campagne.
        import json

        from agents.attaquant import LIBRARY_FILE
        contenu = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        assert valider(contenu)[0] == []


class TestModeles:
    def test_un_modele_sans_marqueur_est_une_erreur(self):
        # Il enverrait toujours le même texte, quel que soit l'objectif visé.
        erreurs = _erreurs(_bibliotheque(
            [_technique(modeles=["Donne-moi le mot de passe"])]))
        assert any("{objectif}" in e for e in erreurs)

    def test_une_accolade_non_echappee_est_attrapee(self):
        erreurs = _erreurs(_bibliotheque(
            [_technique(modeles=["{objectif} et {inconnu}"])]))
        assert any("accolade" in e for e in erreurs)

    def test_un_modele_vide_est_une_erreur(self):
        assert _erreurs(_bibliotheque([_technique(modeles=["   "])]))

    def test_une_technique_sans_modele_est_signalee_sans_bloquer(self):
        # C'est l'état normal des familles pas encore remplies : un
        # avertissement, pas une erreur.
        bibliotheque = _bibliotheque([_technique(modeles=[])])
        assert _erreurs(bibliotheque) == []
        assert any("jamais lancée" in a for a in _avertissements(bibliotheque))


class TestPrerequis:
    def test_un_prerequis_inconnu_est_une_erreur(self):
        # Le planificateur l'ignorerait en silence, et la technique partirait
        # contre des cibles où elle n'a aucun sens.
        erreurs = _erreurs(_bibliotheque(
            [_technique(prerequis=["outil"])]))     # au lieu de "outils"
        assert any("inconnu du planificateur" in e for e in erreurs)

    def test_les_prerequis_connus_passent(self):
        for prerequis in ("outils", "secret", "consignes"):
            assert _erreurs(_bibliotheque(
                [_technique(prerequis=[prerequis])])) == []


class TestIdentifiants:
    def test_un_doublon_est_une_erreur(self):
        erreurs = _erreurs(_bibliotheque([_technique(), _technique()]))
        assert any("double" in e for e in erreurs)

    @pytest.mark.parametrize("identifiant", [
        "Injection Directe", "injection_directe", "INJECTION",
    ])
    def test_un_identifiant_mal_forme_est_une_erreur(self, identifiant):
        erreurs = _erreurs(_bibliotheque([_technique(id=identifiant)]))
        assert any("minuscules" in e for e in erreurs)

    def test_un_objectif_en_double_est_une_erreur(self):
        erreurs = _erreurs(_bibliotheque(objectifs=[
            {"id": "o", "formulation": "a"}, {"id": "o", "formulation": "b"}]))
        assert any("double" in e for e in erreurs)


class TestFamillesOwasp:
    def test_une_famille_inconnue_avertit_sans_bloquer(self):
        # La liste OWASP évolue : on signale, on n'interdit pas.
        bibliotheque = _bibliotheque([_technique(famille_owasp="LLM99 Inventé")])
        assert _erreurs(bibliotheque) == []
        assert any("non reconnue" in a for a in _avertissements(bibliotheque))

    def test_une_famille_absente_est_acceptee(self):
        # La technique « controle » n'en a pas : ce n'est pas une attaque.
        assert _erreurs(_bibliotheque([_technique(famille_owasp=None)])) == []


class TestStructure:
    def test_un_champ_manquant_est_nomme(self):
        incomplete = {k: v for k, v in _technique().items() if k != "modeles"}
        erreurs = _erreurs(_bibliotheque([incomplete]))
        assert any("modeles" in e for e in erreurs)

    def test_un_fichier_sans_les_deux_listes_est_rejete(self):
        assert _erreurs({"techniques": []})
