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
from payloads.exporter_garak import principal as exporter
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


class TestFraicheur:
    """
    garak publie environ tous les 37 jours (médiane mesurée le 2026-11-10 sur
    ses douze dernières versions). Un instantané vieux de plusieurs mois a
    donc manqué des sondes — on le signale sans rien bloquer.
    """

    def _instantane_date(self, instantane, jours):
        from datetime import datetime, timedelta
        import json as _json
        chemin = instantane([_sonde()])
        contenu = _json.loads(chemin.read_text(encoding="utf-8"))
        contenu["exporte_le"] = (
            datetime.now() - timedelta(days=jours)).isoformat(timespec="seconds")
        chemin.write_text(_json.dumps(contenu), encoding="utf-8")

    def test_l_age_est_calcule(self, instantane):
        self._instantane_date(instantane, 42)
        assert charger_bibliotheque()["_garak"]["age_jours"] == 42

    def test_un_instantane_recent_ne_declenche_rien(self, instantane):
        self._instantane_date(instantane, 3)
        avertissements = valider(charger_bibliotheque())[1]
        assert not any("vieux de" in a for a in avertissements)

    def test_un_instantane_ancien_est_signale(self, instantane):
        self._instantane_date(instantane, 95)
        avertissements = valider(charger_bibliotheque())[1]
        assert any("vieux de 95 jours" in a for a in avertissements)

    def test_une_date_illisible_ne_fait_pas_tomber_le_chargement(
            self, instantane, monkeypatch):
        import json as _json
        chemin = instantane([_sonde()])
        contenu = _json.loads(chemin.read_text(encoding="utf-8"))
        contenu["exporte_le"] = "pas une date"
        chemin.write_text(_json.dumps(contenu), encoding="utf-8")
        assert charger_bibliotheque()["_garak"]["age_jours"] is None


class TestExportVide:
    def test_un_export_sans_sonde_ne_remplace_pas_l_instantane(
            self, monkeypatch, tmp_path):
        """
        Si garak réorganise son API privée, la collecte peut ne plus rien
        ramener SANS lever d'exception. Écraser alors l'instantané priverait
        les campagnes de leurs payloads, et un « aucun constat » passerait
        pour un bon résultat.
        """
        import sys
        import types

        import payloads.exporter_garak as module
        faux = types.ModuleType("garak")
        faux.__version__ = "0.17.1"
        monkeypatch.setitem(sys.modules, "garak", faux)
        monkeypatch.setattr(module, "collecter",
                            lambda **k: ([], [{"nom": "x", "motif": "y"}]))

        sortie = tmp_path / "garak.json"
        assert exporter(["--sortie", str(sortie)]) == 1
        assert not sortie.exists()


class TestDetectionDeVersion:
    """
    On DÉTECTE qu'une mise à jour existe ; on ne la fait pas. Automatiser la
    mise à jour casserait la reproductibilité (deux campagnes identiques
    doivent envoyer les mêmes payloads), exigerait les 164 dépendances de
    garak dans le venv du projet, téléchargerait des gigaoctets pendant une
    mission, et enverrait à la cible du contenu non relu.
    """

    @pytest.mark.parametrize("locale, distante, attendu", [
        ("0.17.1", "0.18.0", True),
        ("0.9.0", "0.17.1", True),      # comparaison numérique, pas textuelle
        ("0.17.1", "0.17.1", False),
        ("0.18.0", "0.17.1", False),
    ])
    def test_le_retard_est_detecte(self, monkeypatch, locale, distante,
                                   attendu):
        import payloads.source_garak as source
        monkeypatch.setattr(source, "derniere_version", lambda delai=10: distante)
        assert source.comparer_a_l_instantane(locale)[1] is attendu

    def test_un_reseau_indisponible_ne_bloque_rien(self, monkeypatch):
        # Une campagne ne doit pas dépendre de GitHub.
        import payloads.source_garak as source
        monkeypatch.setattr(source, "_recuperer",
                            lambda *a, **k: (_ for _ in ()).throw(
                                RuntimeError("hors ligne")))
        assert source.derniere_version() is None
        assert source.comparer_a_l_instantane("0.17.1") == (None, False)


class TestProvenanceDansLeRapport:
    def _rapport(self, payloads):
        from rapport import construire, rendre_markdown
        return rendre_markdown(construire({
            "statut": "aucun_constat", "fiche": None,
            "plan": {"essais": [], "ecartees": []}, "constats": [],
            "journal": {}, "ecourtee": None, "payloads": payloads},
            cible="essai"))

    def test_le_rapport_dit_avec_quoi_il_a_teste(self):
        texte = self._rapport({"version": "0.17.1", "sondes": 52,
                               "age_jours": 3, "perime": False})
        assert "garak 0.17.1" in texte and "52 sonde(s)" in texte

    def test_une_bibliotheque_vieillissante_est_signalee(self):
        # Un « aucun constat » obtenu avec des payloads de trois mois ne dit
        # pas la même chose qu'avec des payloads du jour.
        texte = self._rapport({"version": "0.14.0", "sondes": 48,
                               "age_jours": 94, "perime": True})
        assert "vieillissante" in texte

    def test_sans_instantane_aucune_ligne_parasite(self):
        assert "Payloads :" not in self._rapport(None)


class TestPerimetre:
    def test_les_sujets_hors_perimetre_sont_nommes(self):
        # Ils mesurent la modération du modèle, pas sa résistance à
        # l'injection, et l'arbitre n'a aucun critère pour les juger.
        assert "harmful_behaviors.json" in HORS_SUJET
        assert all(raison for raison in HORS_SUJET.values())
