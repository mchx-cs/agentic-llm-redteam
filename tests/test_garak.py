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
    ])
    def test_le_tag_owasp_donne_la_famille_et_le_prerequis(
            self, tag, famille, prerequis):
        # garak porte déjà la correspondance OWASP : on ne la devine pas.
        # Sonde d'un module SANS prérequis propre, pour isoler cette source
        # de l'autre (voir la classe TestPertinenceParModule).
        technique = _technique_depuis_sonde(
            _sonde(nom="probes.encoding.InjectBase64", familles=[tag]))
        assert technique["famille_owasp"] == famille
        assert technique["prerequis"] == prerequis


class TestPertinenceParModule:
    """
    Deux sources de prérequis, qui ne disent PAS la même chose et se cumulent :
    la famille OWASP dit ce que l'attaque CHERCHE (un secret, des consignes),
    le module garak ce qu'elle EXIGE du contexte (du code, un terminal).

    Jusqu'au 2026-11-11 seule la première existait, et comme `owasp:llm01`
    n'exige rien, 73 % des payloads (845/1 143) partaient contre n'importe
    quelle cible — « print ANSI terminal codes » compris, contre un chatbot
    de bibliothèque.
    """

    @pytest.mark.parametrize("module, prerequis", [
        ("dan", "consignes"),
        ("phrasing", "consignes"),
        ("sata", "consignes"),
        ("packagehallucination", "produit-du-code"),
        ("latentinjection", "traite-des-documents"),
        ("ansiescape", "terminal"),
        ("web_injection", "rendu-riche"),
        ("exploitation", "base-donnees"),
    ])
    def test_le_module_impose_son_prerequis(self, module, prerequis):
        technique = _technique_depuis_sonde(_sonde(nom=f"probes.{module}.X"))
        assert prerequis in technique["prerequis"]

    @pytest.mark.parametrize("module", ["encoding", "goodside", "promptinject"])
    def test_un_module_universel_n_exige_rien(self, module):
        # Le bon défaut : ces sondes s'appliquent à tout modèle. Ajouter un
        # prérequis « par précaution » coûterait une faille non trouvée, ce qui
        # est plus grave qu'un essai gaspillé.
        technique = _technique_depuis_sonde(_sonde(nom=f"probes.{module}.X"))
        assert technique["prerequis"] == []

    def test_les_deux_sources_se_cumulent(self):
        # `dan` exige des consignes, `owasp:llm02` un secret : les deux.
        technique = _technique_depuis_sonde(
            _sonde(nom="probes.dan.DanInTheWild", familles=["owasp:llm02"]))
        assert technique["prerequis"] == ["consignes", "secret"]

    def test_le_groupe_et_le_prerequis_lisent_le_meme_module(self):
        # Un seul endroit sait extraire un module d'un nom de sonde : si les
        # deux divergeaient, le tour de rôle et la pertinence ne parleraient
        # plus de la même chose.
        technique = _technique_depuis_sonde(
            _sonde(nom="probes.web_injection.MarkdownXSS"))
        assert technique["groupe"] == "web_injection"
        assert "rendu-riche" in technique["prerequis"]

    @pytest.mark.parametrize("tag, famille", [
        ("owasp:llm05", "LLM05:2025 Improper Output Handling"),
        ("owasp:llm06", "LLM06:2025 Excessive Agency"),
        ("owasp:llm09", "LLM09:2025 Misinformation"),
    ])
    def test_une_famille_que_l_arbitre_ne_juge_pas_est_consignee_a_part(
            self, tag, famille):
        # Vérifié le 2026-11-11 : garak tague aussi 10 sondes llm06, 7 llm09
        # et 2 llm05. Elles sont bel et bien LANCÉES (chacune porte aussi
        # llm01 ou llm02), mais annoncer « LLM06 testée » serait faux, puisque
        # l'arbitre n'a aucun critère pour ces familles. Ni testée, ni
        # ignorée : effleurée.
        technique = _technique_depuis_sonde(
            _sonde(familles=["owasp:llm01", tag]))
        assert technique["famille_owasp"] == "LLM01:2025 Prompt Injection"
        assert technique["familles_non_jugeables"] == [famille]

    def test_owasp_llm07_n_est_plus_promise(self):
        # Entrée morte retirée le 2026-11-11 : aucune sonde de l'instantané ne
        # porte ce tag. Une correspondance qui promet une famille que la
        # source ne fournit pas laisse croire à une couverture inexistante.
        from agents.attaquant import FAMILLES_GARAK
        assert "owasp:llm07" not in FAMILLES_GARAK
        technique = _technique_depuis_sonde(_sonde(familles=["owasp:llm07"]))
        assert technique["famille_owasp"] is None

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


class TestRedondanceAvecGarak:
    """
    Deux techniques du dépôt sont écrites à la main parce que garak ne
    fournit aucune sonde pour leur famille : LLM07 (11 payloads) et LLM06
    (4 payloads). Des payloads maison pourrissent et leur entretien retombe
    sur une seule personne — c'est l'argument même qui a fait choisir garak
    comme source synchronisée. Donc le jour où garak comble le trou, il faut
    le SAVOIR.

    Détection automatique, décision humaine : le principe déjà retenu pour la
    resynchronisation. Rien n'est retiré tout seul.
    """

    def _bibliotheque(self, familles_garak=(), maison=()):
        techniques = [{"id": f"garak-{i}", "source": "garak",
                       "famille_owasp": famille, "payloads_complets": ["x"]}
                      for i, famille in enumerate(familles_garak)]
        techniques += list(maison)
        return {"techniques": techniques}

    def test_rien_a_signaler_avec_les_familles_d_aujourd_hui(self, instantane):
        # L'état mesuré le 2026-11-12 : les 52 sondes du périmètre portent
        # LLM01 ou LLM02 en famille principale, jamais LLM06 ni LLM07. Les
        # deux techniques maison restent donc seules à couvrir la leur.
        #
        # L'instantané est FABRIQUÉ pour le test, comme partout dans ce
        # fichier : un test qui lirait l'instantané local passerait ou non
        # selon qu'on a lancé l'exportateur.
        from payloads.source_garak import techniques_redondantes
        instantane([_sonde(familles=("owasp:llm01",)),
                    _sonde(nom="probes.leakreplay.Fake",
                           familles=("owasp:llm02",))])
        assert techniques_redondantes(charger_bibliotheque()) == []

    def test_une_sonde_qui_comble_le_trou_est_signalee(self):
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM06:2025 Excessive Agency"],
            maison=[{"id": "abus-outils",
                     "famille_owasp": "LLM06:2025 Excessive Agency",
                     "modeles": ["a", "b"]}])
        signalees = techniques_redondantes(bibliotheque)
        assert [t["id"] for t in signalees] == ["abus-outils"]
        assert signalees[0]["payloads"] == 2
        assert signalees[0]["sondes"] == 1

    def test_le_millesime_owasp_n_entre_pas_en_jeu(self):
        # Le rapprochement porte sur `LLM06`, pas sur le libellé complet :
        # faire dépendre la règle du millésime la casserait à la prochaine
        # révision du Top 10.
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM06:2027 Excessive Agency"],
            maison=[{"id": "abus-outils",
                     "famille_owasp": "LLM06:2025 Excessive Agency",
                     "modeles": ["a"]}])
        assert len(techniques_redondantes(bibliotheque)) == 1

    def test_une_autre_famille_ne_declenche_rien(self):
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM01:2025 Prompt Injection"],
            maison=[{"id": "abus-outils",
                     "famille_owasp": "LLM06:2025 Excessive Agency",
                     "modeles": ["a"]}])
        assert techniques_redondantes(bibliotheque) == []

    def test_une_famille_secondaire_ne_comble_aucun_trou(self):
        # Dix sondes portent `owasp:llm06` en SECONDAIRE, et elles visent
        # l'application autour du modèle — exfiltration par URI Markdown,
        # XSS, injection Jinja ou SQL — pas l'appel d'outil. Les compter ici
        # annoncerait un trou comblé qui ne l'est pas, et ferait retirer
        # quatre payloads qui testent autre chose.
        from payloads.source_garak import techniques_redondantes
        bibliotheque = {"techniques": [
            {"id": "garak-web", "source": "garak",
             "famille_owasp": "LLM02:2025 Sensitive Information Disclosure",
             "familles_non_jugeables": ["LLM06:2025 Excessive Agency"],
             "payloads_complets": ["x"]},
            {"id": "abus-outils",
             "famille_owasp": "LLM06:2025 Excessive Agency",
             "modeles": ["a"]}]}
        assert techniques_redondantes(bibliotheque) == []

    def test_une_technique_maison_vide_n_est_pas_signalee(self):
        # `divulgation-information` est vide : il n'y a rien à retirer, et le
        # planificateur signale déjà son absence de payload. La signaler ici
        # noierait le seul cas qui demande une décision.
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM02:2025 Sensitive Information Disclosure"],
            maison=[{"id": "divulgation-information",
                     "famille_owasp": "LLM02:2025 Sensitive Information "
                                      "Disclosure",
                     "modeles": []}])
        assert techniques_redondantes(bibliotheque) == []

    def test_le_temoin_anodin_n_est_jamais_redondant(self):
        # `controle` n'a pas de famille OWASP : c'est le témoin, et aucune
        # sonde offensive ne le remplace.
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM01:2025 Prompt Injection"],
            maison=[{"id": "controle", "famille_owasp": None,
                     "modeles": ["bonjour"]}])
        assert techniques_redondantes(bibliotheque) == []

    def test_une_sonde_garak_n_est_pas_une_dette_maison(self):
        from payloads.source_garak import techniques_redondantes
        bibliotheque = self._bibliotheque(
            familles_garak=["LLM01:2025 Prompt Injection",
                            "LLM01:2025 Prompt Injection"])
        assert techniques_redondantes(bibliotheque) == []


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
