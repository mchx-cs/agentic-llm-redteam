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

import json
from datetime import date, datetime
from pathlib import Path

FICHIER_AUTORISATION = "autorisation.json"

CHAMPS_OBLIGATOIRES = ("cible", "autorise_par", "reference", "debut", "fin")

# Une cible locale est à vous par construction : aucun mandat à produire.
_MARQUES_LOCALES = ("localhost", "127.0.0.1", "[::1]")


class AutorisationManquante(RuntimeError):
    """Pas de mandat valide pour cette cible : la campagne ne démarre pas."""


def est_locale(nom_cible):
    """Une cible livrée avec le projet, ou servie depuis cette machine."""
    if nom_cible in ("leurre", "mock"):
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


class PisteAudit:
    """
    Journal rejouable des échanges avec la cible, écrit au fil de l'eau.

    On consigne ce qu'on a envoyé au système du CLIENT, pas nos appels
    internes au juge : c'est ce qu'on doit pouvoir montrer si la campagne est
    contestée. Les appels au modèle, eux, sont comptés par `llm_client`.

    Chaque ligne est un JSON autonome (format JSONL) : le fichier reste
    lisible même si la campagne s'interrompt en plein milieu.
    """

    def __init__(self, chemin, cible, autorisation=None):
        self.chemin = Path(chemin)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._fichier = self.chemin.open("a", encoding="utf-8")
        self._ecrire({
            "type": "debut_campagne",
            "cible": cible,
            # None pour une cible locale : on le dit explicitement, plutôt
            # que de laisser croire à un mandat absent par oubli.
            "autorisation": autorisation or "cible locale, aucun mandat requis",
        })

    def _ecrire(self, entree):
        entree = {"horodatage": datetime.now().isoformat(timespec="seconds"),
                  **entree}
        self._fichier.write(json.dumps(entree, ensure_ascii=False) + "\n")
        # Vidage immédiat : une campagne qui tombe doit laisser sa trace.
        self._fichier.flush()

    def consigner_echange(self, phase, envoye, recu, tronquee=False):
        """Un aller-retour avec la cible : reconnaissance, attaque ou rejeu."""
        self._ecrire({"type": "echange", "phase": phase, "envoye": envoye,
                      "recu": recu, "tronquee": tronquee})

    def consigner_verdict(self, essai, verdict):
        self._ecrire({"type": "verdict", "essai": essai,
                      "enfreint": verdict["reussi"],
                      "critere": verdict["critere"],
                      "votes": verdict.get("votes")})

    def clore(self, statut, journal):
        self._ecrire({"type": "fin_campagne", "statut": statut,
                      "appels": journal.get("appels"),
                      "tokens": journal.get("tokens")})
        self._fichier.close()

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
