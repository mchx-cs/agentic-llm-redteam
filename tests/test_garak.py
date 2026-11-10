"""
Tests de la source garak : traduction d'une sonde et fusion de l'instantané.

Aucun appel à garak ici, et c'est le but : le projet doit fonctionner
IDENTIQUEMENT avec ou sans instantané. Celui-ci est optionnel par
construction — on fabrique donc des instantanés de test à la main.
"""

import json

import pytest

import agents.attaquant
from agents.attaquant import _technique_depuis_sonde, charger_bibliotheque
from payloads.source_garak import HORS_SUJET
from payloads.valider import valider


def _sonde(nom="probes.dan.DanInTheWild", familles=("owasp:llm01",),
           payloads=("prompt un", "prompt deux")):
    return {"sonde": nom, "objectif": "disregard the system prompt",
            "familles_owasp": list(familles), "langue": "en", "doc": "",
            "payloads": list(payloads), "payloads_disponibles": len(payloads)}


@pytest.fixture
def instantane(monkeypatch, tmp_path):
    """Installe un instantané garak fabriqué pour le test."""
    def installer(sondes):
        chemin = tmp_path / "garak.json"
        chemin.write_text(json.dumps({
            "version_garak": "0.17.1", "exporte_le": "2026-11-10T00:00:00",
            "sondes": sondes, "ecartees": []}), encoding="utf-8")
        monkeypatch.setattr(agents.attaquant, "FICHIER_GARAK", chemin)
        return chemin
    return installer


@pytest.fixture
def sans_instantane(monkeypatch, tmp_path):
    monkeypatch.setattr(agents.attaquant, "FICHIER_GARAK",
                        tmp_path / "absent.json")


class TestTraductionDUneSonde:
    def test_l_identifiant_respecte_le_format_du_projet(self):
        # Le validateur impose minuscules, chiffres et tirets.
        technique = _technique_depuis_sonde(_sonde())
        assert technique["id"] == "garak-dan-daninthewild"

    @pytest.mark.parametrize("tag, famille, prerequis", [
        ("owasp:llm01", "LLM01:2025 Prompt Injection", []),
        ("owasp:llm02", "LLM02:2025 Sensitive Information Disclosure",
         ["secret"]),
        ("owasp:llm07", "LLM07:2025 System Prompt Leakage", ["consignes"]),
    ])
    def test_le_tag_owasp_donne_la_famille_et_le_prerequis(
            self, tag, famille, prerequis):
        # garak porte déjà la correspondance OWASP : on ne la devine pas.
        technique = _technique_depuis_sonde(_sonde(familles=[tag]))
        assert technique["famille_owasp"] == famille
        assert technique["prerequis"] == prerequis

    def test_les_prompts_vont_dans_payloads_complets_pas_dans_modeles(self):
        # Ce sont des prompts entiers : sans `{objectif}`, ils échoueraient
        # à la validation s'ils atterrissaient dans `modeles`.
        technique = _technique_depuis_sonde(_sonde())
        assert technique["modeles"] == []
        assert technique["payloads_complets"] == ["prompt un", "prompt deux"]

    def test_la_provenance_est_conservee(self):
        # Pour que le rapport puisse citer la sonde d'origine.
        assert _technique_depuis_sonde(_sonde())["source"] == \
               "garak probes.dan.DanInTheWild"

    def test_une_sonde_traduite_passe_le_validateur(self):
        bibliotheque = {"techniques": [_technique_depuis_sonde(_sonde())],
                        "objectifs": [{"id": "o", "formulation": "f"}]}
        assert valider(bibliotheque)[0] == []


class TestFusion:
    def test_sans_instantane_la_bibliotheque_est_inchangee(self, sans_instantane):
        # Le dépôt doit tourner exactement comme avant pour qui ne
        # synchronise pas.
        assert "_garak" not in charger_bibliotheque()

    def test_avec_instantane_les_sondes_sont_ajoutees(self, instantane):
        instantane([_sonde(), _sonde(nom="probes.encoding.InjectBase64")])
        bibliotheque = charger_bibliotheque()
        identifiants = {t["id"] for t in bibliotheque["techniques"]}
        assert "garak-dan-daninthewild" in identifiants
        assert "garak-encoding-injectbase64" in identifiants
        # Les techniques écrites à la main restent présentes.
        assert "controle" in identifiants

    def test_la_version_de_garak_est_consignee(self, instantane):
        # Une campagne doit rester rattachable à une version de la source.
        instantane([_sonde()])
        assert charger_bibliotheque()["_garak"]["version"] == "0.17.1"

    def test_avec_garak_peut_etre_desactive(self, instantane):
        instantane([_sonde()])
        assert "_garak" not in charger_bibliotheque(avec_garak=False)

    def test_la_bibliotheque_fusionnee_reste_valide(self, instantane):
        instantane([_sonde(), _sonde(nom="probes.leakreplay.Guardrail",
                                     familles=["owasp:llm02"])])
        assert valider(charger_bibliotheque())[0] == []


class TestPerimetre:
    def test_les_sujets_hors_perimetre_sont_nommes(self):
        # Ils mesurent la modération du modèle, pas sa résistance à
        # l'injection, et l'arbitre n'a aucun critère pour les juger.
        assert "harmful_behaviors.json" in HORS_SUJET
        assert all(raison for raison in HORS_SUJET.values())
