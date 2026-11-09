"""
evaluation/etiqueter.py — Étiqueter à la main les échanges collectés.

Modifier a_etiqueter.json à la main, c'est long et on y fait des fautes de
frappe silencieuses ("dev " au lieu de "dev", un true oublié). Cet outil
affiche chaque échange, pose les questions une par une, valide les réponses,
et enregistre au fur et à mesure : on peut s'arrêter et reprendre plus tard.

Règle NON NÉGOCIABLE : l'avis de l'arbitre n'est jamais affiché. Les
étiquettes sont la vérité terrain ; les voir influencées par le juge
reviendrait à mesurer le juge contre lui-même.

Le jeu ('dev' ou 'test') se choisit par GROUPE, pas par échange : toutes les
réponses à un même payload partent ensemble, sinon le jeu de test
contiendrait une simple reformulation d'un cas du jeu de dev.

Lance-le depuis la racine du projet avec :
    python -m evaluation.etiqueter              # étiqueter les échanges restants
    python -m evaluation.etiqueter --integrer   # verser les étiquetés dans le corpus
"""

import argparse
import json
from pathlib import Path

DOSSIER = Path(__file__).parent
FICHIER_A_ETIQUETER = DOSSIER / "a_etiqueter.json"
FICHIER_CORPUS = DOSSIER / "echanges_etiquetes.json"

# Les catégories déjà utilisées dans le corpus. En proposer une liste évite
# d'inventer un synonyme ("fuite_directe", "fuite directe"…) qui empêcherait
# ensuite de regrouper les erreurs par type de piège.
CATEGORIES = [
    "controle",
    "refus-mentionne-secret",
    "fuite-directe",
    "fuite-epelee",
    "fuite-encodee",
    "fuite-indice",
    "fuite-prompt-systeme",
    "hallucination",
    "obeissance",
    "obeissance-refusee",
    "jeu-de-role-anodin",
]


def charger(fichier):
    with open(fichier, encoding="utf-8") as f:
        return json.load(f)


def enregistrer(fichier, donnees):
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=2)


def demander_choix(question, options):
    """Pose une question à choix multiple. Renvoie None si on veut passer."""
    print(f"\n{question}")
    for numero, option in enumerate(options, start=1):
        print(f"  {numero}. {option}")
    print("  p. passer cet échange    q. quitter (le travail est enregistré)")

    # Boucle bornée par la sortie : 'p' passe, 'q' quitte. Pas d'infini caché.
    while True:
        saisie = input("> ").strip().lower()
        if saisie == "q":
            raise KeyboardInterrupt
        if saisie == "p":
            return None
        if saisie.isdigit() and 1 <= int(saisie) <= len(options):
            return options[int(saisie) - 1]
        print(f"Réponds par un nombre entre 1 et {len(options)}, ou p / q.")


def afficher_echange(echange, position, total):
    print("\n" + "=" * 70)
    print(f"[{position}/{total}]  {echange['id']}   (groupe {echange['groupe']})")
    print(f"Secret du chatbot : {echange['secret']}")
    print(f"Provenance        : {echange.get('source', '—')}")
    print("-" * 70)
    print(f"Utilisateur : {echange['payload']}")
    print(f"Chatbot     : {echange['reponse']}")
    print("=" * 70)


def etiqueter():
    donnees = charger(FICHIER_A_ETIQUETER)
    echanges = donnees["echanges"]
    restants = [e for e in echanges if e["attendu"] is None]

    if not restants:
        print("Tous les échanges sont déjà étiquetés. "
              "Lance --integrer pour les verser dans le corpus.")
        return

    print(f"{len(restants)} échange(s) à étiqueter sur {len(echanges)}.")
    print("L'avis de l'arbitre n'est pas affiché : c'est voulu.")

    # Un groupe déjà étiqueté impose son jeu aux échanges suivants du même
    # groupe : le script d'évaluation refuse un groupe réparti entre dev et test.
    jeu_du_groupe = {e["groupe"]: e["jeu"] for e in echanges if e["jeu"]}

    try:
        for echange in restants:
            position = echanges.index(echange) + 1
            afficher_echange(echange, position, len(echanges))

            verdict = demander_choix(
                "Le chatbot a-t-il enfreint ses règles ?",
                ["non — pas de faille", "oui — faille"],
            )
            if verdict is None:
                continue

            categorie = demander_choix("Catégorie de piège ?", CATEGORIES)
            if categorie is None:
                continue

            groupe = echange["groupe"]
            if groupe in jeu_du_groupe:
                jeu = jeu_du_groupe[groupe]
                print(f"\nJeu : {jeu} (imposé par le groupe {groupe}).")
            else:
                jeu = demander_choix(
                    "Quel jeu ? (dev = pour régler l'arbitre, "
                    "test = gelé, pour mesurer)",
                    ["dev", "test"],
                )
                if jeu is None:
                    continue
                jeu_du_groupe[groupe] = jeu

            print("\nEn une phrase, ce que ce cas teste (vide = la provenance) :")
            piege = input("> ").strip() or echange.get("source", "")

            echange["attendu"] = verdict.startswith("oui")
            echange["categorie"] = categorie
            echange["jeu"] = jeu
            echange["piege"] = piege

            # Enregistrement après CHAQUE échange : une interruption ne
            # fait jamais perdre le travail déjà fait.
            enregistrer(FICHIER_A_ETIQUETER, donnees)
            print(f"-> {echange['id']} enregistré.")

    except KeyboardInterrupt:
        print("\n\nInterrompu. Le travail déjà fait est enregistré.")

    etiquetes = sum(1 for e in echanges if e["attendu"] is not None)
    print(f"\n{etiquetes}/{len(echanges)} échange(s) étiqueté(s).")
    if etiquetes == len(echanges):
        print("Terminé : lance --integrer pour les verser dans le corpus.")


def integrer():
    """Verse les échanges étiquetés dans echanges_etiquetes.json."""
    donnees = charger(FICHIER_A_ETIQUETER)
    corpus = charger(FICHIER_CORPUS)

    prets = [e for e in donnees["echanges"] if e["attendu"] is not None]
    if not prets:
        print("Aucun échange étiqueté à intégrer.")
        return

    deja = {e["id"] for e in corpus["echanges"]}
    # Un groupe déjà présent dans le corpus impose son jeu : on refuse plutôt
    # que de créer silencieusement une fuite entre les jeux dev et test.
    jeu_du_groupe = {e["groupe"]: e["jeu"] for e in corpus["echanges"]}

    ajoutes = 0
    for echange in prets:
        if echange["id"] in deja:
            print(f"{echange['id']} : déjà dans le corpus, ignoré.")
            continue
        attendu = jeu_du_groupe.get(echange["groupe"])
        if attendu and attendu != echange["jeu"]:
            print(f"{echange['id']} : le groupe {echange['groupe']} est déjà "
                  f"en '{attendu}', pas en '{echange['jeu']}'. Ignoré.")
            continue
        corpus["echanges"].append(echange)
        jeu_du_groupe[echange["groupe"]] = echange["jeu"]
        ajoutes += 1

    enregistrer(FICHIER_CORPUS, corpus)
    restants = [e for e in donnees["echanges"] if e["attendu"] is None]
    donnees["echanges"] = restants
    enregistrer(FICHIER_A_ETIQUETER, donnees)

    print(f"{ajoutes} échange(s) ajouté(s) au corpus "
          f"({len(corpus['echanges'])} au total).")
    if restants:
        print(f"{len(restants)} échange(s) restent à étiqueter.")


if __name__ == "__main__":
    parseur = argparse.ArgumentParser(
        description="Étiqueter à la main les échanges collectés.")
    parseur.add_argument("--integrer", action="store_true",
                         help="verser les échanges étiquetés dans le corpus")
    arguments = parseur.parse_args()
    integrer() if arguments.integrer else etiqueter()
