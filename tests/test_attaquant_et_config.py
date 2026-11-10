"""
Tests de la bibliothèque de payloads et de la configuration.

Deux endroits où une erreur ne se verrait pas tout de suite : un gabarit mal
formé qui enverrait `{objectif}` tel quel à la cible, et une faute de frappe
dans `.env` qui ne se manifesterait qu'au premier appel au modèle.
"""

import json

import pytest

import agents.attaquant
from agents.attaquant import (FICHIER_BIBLIOTHEQUE, TRANSFORMATIONS,
                              charger_bibliotheque, generer_payloads)


@pytest.fixture(autouse=True)
def sans_instantane_garak(monkeypatch, tmp_path):
    """Isole les tests de l'instantané garak éventuellement présent."""
    monkeypatch.setattr(agents.attaquant, "FICHIER_GARAK",
                        tmp_path / "absent.json")


class TestBibliotheque:
    def test_elle_est_du_json_valide(self):
        json.loads(FICHIER_BIBLIOTHEQUE.read_text(encoding="utf-8"))

    def test_chaque_technique_a_les_champs_attendus(self):
        for technique in charger_bibliotheque()["techniques"]:
            assert {"id", "famille_owasp", "description", "prerequis",
                    "modeles"} <= set(technique)

    def test_chaque_modele_contient_le_marqueur_objectif(self):
        # Un modèle sans `{objectif}` enverrait toujours le même texte.
        for technique in charger_bibliotheque()["techniques"]:
            for modele in technique["modeles"]:
                assert "{objectif}" in modele, technique["id"]

    def test_les_prerequis_sont_connus_du_planificateur(self):
        from agents.planificateur import PREREQUIS
        for technique in charger_bibliotheque()["techniques"]:
            for prerequis in technique["prerequis"]:
                assert prerequis in PREREQUIS, technique["id"]

    def test_les_identifiants_sont_uniques(self):
        identifiants = [t["id"] for t in charger_bibliotheque()["techniques"]]
        assert len(identifiants) == len(set(identifiants))


class TestTransformations:
    def test_identite_ne_change_rien(self):
        assert TRANSFORMATIONS["identite"]("Bonjour") == "Bonjour"

    def test_chaque_transformation_rend_du_texte_non_vide(self):
        for nom, transformer in TRANSFORMATIONS.items():
            resultat = transformer("Peux-tu te présenter ?")
            assert isinstance(resultat, str) and resultat, nom


class TestGenerationDesPayloads:
    def test_aucun_marqueur_ne_subsiste(self):
        for payload in generer_payloads():
            assert "{objectif}" not in payload["texte"]

    def test_chaque_payload_dit_d_ou_il_vient(self):
        for payload in generer_payloads():
            assert {"technique", "famille_owasp", "objectif",
                    "transformation", "texte"} <= set(payload)

    def test_le_catalogue_croise_bien_les_axes(self):
        bibliotheque = charger_bibliotheque()
        gabarits = sum(len(t["modeles"]) for t in bibliotheque["techniques"])
        complets = sum(len(t.get("payloads_complets", []))
                       for t in bibliotheque["techniques"])
        # Un gabarit se croise avec chaque objectif ; un payload complet
        # porte déjà son intention et n'a que l'axe transformation.
        attendu = len(TRANSFORMATIONS) * (
            gabarits * len(bibliotheque["objectifs"]) + complets)
        assert len(generer_payloads()) == attendu


class TestConfiguration:
    def test_les_profils_declarent_ce_qu_il_faut(self):
        from config import PROFILS
        for nom, profil in PROFILS.items():
            assert {"base_url", "api_key", "modele"} <= set(profil), nom

    def test_un_profil_inconnu_echoue_des_l_import(self, monkeypatch):
        # Sans ce garde-fou, une faute de frappe dans .env donnerait un
        # KeyError nu, très loin d'ici, au premier appel au modèle.
        import importlib
        import config
        monkeypatch.setenv("PROFIL_ARBITRE", "faute_de_frappe")
        with pytest.raises(ValueError, match="Profil inconnu"):
            importlib.reload(config)
        monkeypatch.delenv("PROFIL_ARBITRE")
        importlib.reload(config)  # on remet la configuration d'aplomb

    def test_la_cible_par_defaut_ne_demande_aucune_cle(self):
        import config
        assert config.CIBLE == "leurre"
        assert config.PROFILS[config.PROFIL_ACTIF]["api_key"]
