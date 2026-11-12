"""
audit.py — Sous quel mandat on a testé, et ce qu'on a réellement envoyé.

Deux moitiés d'une même exigence : pouvoir prouver que ce qu'on a fait était
autorisé, et pouvoir montrer exactement ce qu'on a fait.

1. **L'autorisation.** Le cadre légal du projet dit que le red teaming de LLM
   n'est licite que contre un système qu'on possède ou qu'on est explicitement
   autorisé à tester. Jusqu'ici c'était une phrase dans un fichier ; ici, c'est
   le code qui refuse de démarrer.

2. **La piste d'audit.** Un fichier JSONL, écrit AU FUR ET À MESURE, qui
   consigne chaque échange avec la cible. Écrire en continu plutôt qu'à la fin
   n'est pas un détail : si la campagne tombe, on garde la trace de ce qui a
   déjà été envoyé — et c'est précisément le moment où on en a besoin.

Le niveau d'exigence suit le risque : le leurre livré et la cible déterministe
ne demandent rien, puisqu'ils sont à vous et tournent en local. Un endpoint
distant, lui, exige un mandat. Imposer le même formulaire aux deux apprendrait
surtout à cliquer sans lire.
"""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

FICHIER_AUTORISATION = "autorisation.json"

CHAMPS_OBLIGATOIRES = ("cible", "autorise_par", "reference", "debut", "fin")

# Une cible locale est à vous par construction : aucun mandat à produire.
_MARQUES_LOCALES = ("localhost", "127.0.0.1", "[::1]")


class AutorisationManquante(RuntimeError):
    """Pas de mandat valide pour cette cible : la campagne ne démarre pas."""


def est_locale(nom_cible):
    """
    Une cible livrée avec le projet, ou servie depuis cette machine.

    Les cibles nommées du paquet `cibles` sont à vous par construction : elles
    tournent en local et ne contiennent que des secrets factices. La liste est
    demandée à `cibles` plutôt que recopiée ici — sinon elle dériverait, et
    une cible livrée finirait par exiger un mandat (c'est arrivé avec `demo`
    le 2026-11-11, ce qui cassait la démonstration en une commande).
    """
    from cibles import est_cible_livree

    if est_cible_livree(nom_cible):
        return True
    return any(marque in nom_cible for marque in _MARQUES_LOCALES)


def _date(valeur, champ):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        raise AutorisationManquante(
            f"Autorisation : '{champ}' doit être une date AAAA-MM-JJ, "
            f"reçu {valeur!r}."
        ) from None


def charger(chemin=FICHIER_AUTORISATION):
    """Lit le fichier d'autorisation, ou explique précisément ce qui manque."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise AutorisationManquante(
            f"Aucune autorisation trouvée ({chemin}).\n"
            f"  Copie autorisation.example.json, remplis-la, et relance.\n"
            f"  Tester un système tiers sans mandat écrit est un délit."
        )
    try:
        autorisation = json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erreur:
        raise AutorisationManquante(
            f"{chemin} n'est pas du JSON valide : {erreur}") from erreur

    manquants = [c for c in CHAMPS_OBLIGATOIRES if not autorisation.get(c)]
    if manquants:
        raise AutorisationManquante(
            f"{chemin} : champ(s) manquant(s) — {', '.join(manquants)}.")
    return autorisation


def verifier(autorisation, nom_cible, aujourd_hui=None):
    """
    Vérifie que le mandat couvre VRAIMENT cette cible, aujourd'hui.

    Les deux contrôles qui comptent : un mandat pour une cible ne vaut pas
    pour une autre, et un mandat expiré ne vaut plus rien. Sans eux, le
    fichier ne serait qu'une case à cocher.
    """
    aujourd_hui = aujourd_hui or date.today()

    portee = autorisation["cible"]
    if portee not in nom_cible:
        raise AutorisationManquante(
            f"L'autorisation couvre '{portee}', or la campagne vise "
            f"'{nom_cible}'.\n"
            f"  Un mandat pour une cible ne vaut pas pour une autre."
        )

    debut = _date(autorisation["debut"], "debut")
    fin = _date(autorisation["fin"], "fin")
    if not debut <= aujourd_hui <= fin:
        raise AutorisationManquante(
            f"L'autorisation court du {debut} au {fin}, or nous sommes le "
            f"{aujourd_hui}.\n"
            f"  Tester hors de la fenêtre convenue n'est pas couvert."
        )
    return autorisation


def exiger(nom_cible, chemin=FICHIER_AUTORISATION):
    """
    Renvoie le mandat couvrant `nom_cible`, ou None si la cible est locale.

    C'est la porte d'entrée de la campagne : elle lève plutôt que de laisser
    partir une attaque non couverte.
    """
    if est_locale(nom_cible):
        return None
    return verifier(charger(chemin), nom_cible)


# --- Chaîne de preuve (manuel OWASP §7.3) ------------------------------------
# « Tag each artifact with a unique Case ID […]. Calculate a SHA-256 hash of
# raw evidence at collection. »
#
# Ce que ces empreintes font, et ce qu'elles ne font pas : elles permettent de
# montrer qu'une piste n'a pas été retouchée entre sa production et sa
# remise, et de citer une preuve par son empreinte sans recopier la réponse
# verbatim d'un client. Elles ne constituent PAS une conservation en lecture
# seule — le manuel l'exige aussi, et c'est une affaire d'infrastructure, pas
# de code.

def empreinte(contenu):
    """SHA-256 d'un texte, en hexadécimal."""
    if contenu is None:
        contenu = ""
    return hashlib.sha256(str(contenu).encode("utf-8")).hexdigest()


def _case_id(cible):
    """
    Identifiant de dossier : horodaté, lisible, et stable pour une campagne.

    Dérivé plutôt qu'aléatoire : un opérateur qui voit « 20261112-174500-demo »
    sait de quelle campagne il s'agit sans rien aller rapprocher. Un UUID
    serait unique mais muet.
    """
    propre = re.sub(r"[^a-zA-Z0-9]+", "-", str(cible)).strip("-").lower()[:40]
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{propre or 'cible'}"


def verifier_sceau(chemin):
    """
    Une piste scellée a-t-elle été modifiée depuis sa clôture ?

    Renvoie (intacte, explication). Utile en mission : si un rapport est
    contesté, on doit pouvoir montrer que la trace n'a pas bougé.
    """
    chemin = Path(chemin)
    lignes = [l for l in chemin.read_text(encoding="utf-8").splitlines() if l]
    if not lignes:
        return (False, "Piste vide.")

    try:
        derniere = json.loads(lignes[-1])
    except json.JSONDecodeError:
        return (False, "Dernière ligne illisible : piste tronquée ou altérée.")

    if derniere.get("type") != "sceau":
        return (False, "Piste non scellée : la campagne ne s'est pas "
                       "terminée proprement, ou le sceau a été retiré.")

    # Le sceau porte sur tout ce qui le précède, retour à la ligne compris.
    avant_sceau = "".join(ligne + "\n" for ligne in lignes[:-1])
    calcule = empreinte(avant_sceau)
    if calcule == derniere.get("empreinte"):
        return (True, f"Piste intacte ({derniere.get('case_id', 'sans ID')}).")
    return (False, "Empreinte NON concordante : la piste a été modifiée "
                   "après sa clôture.")


class PisteAudit:
    """
    Journal rejouable des échanges avec la cible, écrit au fil de l'eau.

    On consigne ce qu'on a envoyé au système du CLIENT, pas nos appels
    internes au juge : c'est ce qu'on doit pouvoir montrer si la campagne est
    contestée. Les appels au modèle, eux, sont comptés par `llm_client`.

    Chaque ligne est un JSON autonome (format JSONL) : le fichier reste
    lisible même si la campagne s'interrompt en plein milieu.
    """

    def __init__(self, chemin, cible, autorisation=None, contexte=None):
        self.chemin = Path(chemin)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        # Identifiant unique de dossier, exigé par le manuel OWASP (§7.3,
        # « Case Identification »). Dérivé de l'horodatage et de la cible, donc
        # reproductible et lisible — pas un UUID opaque qu'il faudrait aller
        # rapprocher d'autre chose.
        self.case_id = _case_id(cible)
        self._empreintes = 0
        self._fichier = self.chemin.open("a", encoding="utf-8")
        self._ecrire({
            "type": "debut_campagne",
            "case_id": self.case_id,
            "cible": cible,
            # None pour une cible locale : on le dit explicitement, plutôt
            # que de laisser croire à un mandat absent par oubli.
            "autorisation": autorisation or "cible locale, aucun mandat requis",
            # Ce qu'on CONTRÔLE de l'environnement de test, et ce qu'on ne
            # contrôle pas. Voir `telemetrie()`.
            "environnement": contexte or {},
        })

    def _ecrire(self, entree):
        entree = {"horodatage": datetime.now().isoformat(timespec="seconds"),
                  **entree}
        self._fichier.write(json.dumps(entree, ensure_ascii=False) + "\n")
        # Vidage immédiat : une campagne qui tombe doit laisser sa trace.
        self._fichier.flush()

    def consigner_echange(self, phase, envoye, recu, tronquee=False):
        """
        Un aller-retour avec la cible : reconnaissance, attaque ou rejeu.

        Chaque échange porte l'empreinte SHA-256 de ce qui a été envoyé et de
        ce qui a été reçu (manuel §7.3, « Integrity Hashing »). Le contenu est
        consigné juste à côté, donc l'empreinte ne protège pas d'une altération
        du fichier entier — c'est la clôture qui s'en charge. Elle sert à autre
        chose : citer une preuve dans un rapport, ou dans un échange avec le
        client, sans recopier une réponse verbatim.
        """
        self._empreintes += 1
        self._ecrire({"type": "echange", "phase": phase, "envoye": envoye,
                      "recu": recu, "tronquee": tronquee,
                      "empreinte_envoye": empreinte(envoye),
                      "empreinte_recu": empreinte(recu)})

    def consigner_verdict(self, essai, verdict):
        self._ecrire({"type": "verdict", "essai": essai,
                      "enfreint": verdict["reussi"],
                      "critere": verdict["critere"],
                      "votes": verdict.get("votes")})

    def clore(self, statut, journal):
        """
        Referme la piste et la SCELLE.

        L'empreinte finale porte sur tout ce qui précède : elle permet de
        montrer qu'une piste produite en mission n'a pas été retouchée après
        coup. Elle est calculée avant d'être écrite, donc elle ne s'inclut pas
        elle-même — sinon le scellement serait impossible à vérifier.
        """
        self._ecrire({"type": "fin_campagne", "statut": statut,
                      "appels": journal.get("appels"),
                      "tokens": journal.get("tokens"),
                      "echanges_consignes": self._empreintes})
        self._fichier.flush()
        sceau = empreinte(self.chemin.read_text(encoding="utf-8"))
        self._ecrire({"type": "sceau", "case_id": self.case_id,
                      "algorithme": "sha256", "empreinte": sceau})
        self._fichier.close()
        return sceau

    def tracer(self, phase, interroger_cible):
        """
        Enveloppe une cible pour que chaque échange soit consigné.

        La cible reste une fonction `message -> str` : les agents qui la
        reçoivent ne savent même pas qu'elle est tracée.
        """
        def interroger(message):
            reponse = interroger_cible(message)
            self.consigner_echange(phase, message, reponse)
            return reponse
        return interroger


# --- Télémétrie : ce qu'on contrôle, et ce qu'on ne contrôle pas -------------
# Manuel §7.3, « Runtime & Environment Telemetry » : model name, version,
# provider, endpoint, generation parameters, context state… puis, et c'est la
# phrase qui compte pour nous :
#
#     « Residual Non-Determinism: If sampling parameters or backend routing
#     cannot be locked, explicitly note the potential for variance during
#     replay. »
#
# Un red teamer en boîte noire ne connaît RIEN de la configuration de sa
# cible : ni son modèle, ni sa température, ni son prompt système — c'est
# précisément ce qu'il cherche. Prétendre la consigner serait inventer. On
# consigne donc ce qu'on sait (le nôtre, et ce qu'on a envoyé), et on DÉCLARE
# ce qu'on ignore, parce qu'une variance non expliquée au rejeu se lirait
# autrement comme un défaut de la mesure.

def telemetrie(nom_cible, profil_cible=None):
    """L'environnement de test, côté connu et côté inconnu."""
    from agents.arbitre import NB_VOTES
    from agents.verificateur import NB_REJEUX
    from config import PROFIL_ACTIF, PROFIL_ARBITRE, PROFILS

    arbitre = PROFILS.get(PROFIL_ARBITRE, {})
    return {
        # Ce que NOUS exécutons : entièrement connu, donc entièrement consigné.
        "nos_modeles": {
            "arbitre": {
                "profil": PROFIL_ARBITRE,
                "modele": arbitre.get("modele"),
                "base_url": arbitre.get("base_url"),
                "temperature": 0,
                "votes_par_verdict": NB_VOTES,
            },
            "profil_actif": PROFIL_ACTIF,
        },
        "cible": {
            "nom": nom_cible,
            "profil_http": profil_cible,
            # Les paramètres de génération de la cible sont HORS de notre
            # portée en boîte noire. Le dire est une information ; l'omettre
            # laisserait croire qu'on les a figés.
            "parametres_de_generation": "inconnus (test en boîte noire)",
        },
        "non_determinisme_residuel": [
            "La cible choisit ses propres paramètres d'échantillonnage : deux "
            "campagnes identiques peuvent donner des verdicts différents.",
            "L'arbitre lui-même n'est pas déterministe à température 0 "
            f"(mesuré) : d'où {NB_VOTES} votes par verdict.",
            f"Une divulgation est rejouée {NB_REJEUX} fois, ce qui mesure la "
            "reproductibilité sans l'éliminer.",
        ],
    }
