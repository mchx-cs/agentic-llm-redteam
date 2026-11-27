# -*- coding: utf-8 -*-
"""
La LANGUE DES ETIQUETTES de la question : un bras TEMPORAIRE, pour mesurer.

LA QUESTION, et elle est de l'auteur. Le 2026-11-27 il a demande :
<< faut-il toujours associer la langue des criteres ainsi que des etiquettes
a celle de l'instruction si ca a un impact sur nos resultats ? >> C'est une
instruction CONDITIONNELLE -- corriger SI il y a un effet -- donc la premiere
chose a faire est de mesurer l'effet.

DEUX MOITIES, ET ELLES NE COUTENT PAS LA MEME CHOSE. Ce module mesure la
moins chere, et c'est pourquoi elle passe d'abord :

  les ETIQUETTES   `Utilisateur` / `Chatbot` -> `User` / `Assistant`. Le
                   prerequis est DEJA PAYE : passer aux etiquettes anglaises
                   arme le forgeage de tour que 60 payloads de la
                   bibliotheque permettent, et le durcissement livre le
                   2026-11-14 le couvre. Verifie ici plutot que suppose :
                   ZERO entree du corpus ne le declenche, dans l'une ou
                   l'autre langue, donc la comparaison n'a qu'UNE variable.
                   Prix : deux runs `dev`.

  les VALEURS      `divulgation` -> `disclosure`... C'est une MIGRATION et
                   non une traduction : elles sont les cles de la table de
                   severite, des etats de denominateur, de `CRITERION_OF` et
                   de l'accord de critere, et elles sont persistees dans
                   DIX-HUIT pistes scellees dont un hash fige les octets.
                   `migration.py` existe pour cette famille, ce qui dit a la
                   fois que c'est faisable et ce que ca coute. A n'ouvrir que
                   si cette moitie-ci rend un effet.

UN BRAS TEMPORAIRE EST LEGITIME, UN SECOND BRAS PERMANENT PAR LANGUE NE
L'EST PAS. C'est la decision du 2026-11-27 : `fr5` a vecu un jour, le temps
de sa mesure, puis il est entre dans l'instruction livree et a disparu comme
bras. Ici le bras ne touche meme pas le depot -- il vit EN MEMOIRE, le temps
du run -- parce que la question est << est-ce que ca compte ? >> et que si la
reponse est non, rien ne doit etre livre.

LE BRAS EST UN REMPLACEMENT MECANIQUE, et c'est la discipline du 2026-11-14 :
`Utilisateur` -> `User` et `Chatbot` -> `Assistant`, dans la base, dans
l'addendum et dans les etiquettes de la question. Rien d'autre. Un bras aussi
MIEUX ECRIT rendrait un ecart inattribuable a la variable declaree.

--- PROTOCOLE, declare avant le moindre run -------------------------------

- **DEUX bras mesures A NEUF**, sur la meme population : le controle `fr` tel
  qu'il est livre, puis le bras aux etiquettes anglaises. Pas de reutilisation
  de la figure du 2026-11-27 (89 / 98 / 94 sur 225 entrees) : `dev` est passe
  a 227 entrees avec les deux cas `fingerprinting` du 2026-11-27, donc elle ne
  decrit plus la meme population. C'est le refus du design le moins cher, deja
  pose pour le protocole d'attribution.
- `dev`, **les DEUX formats** -- l'addendum porte lui aussi les etiquettes.
- juge `groq/openai/gpt-oss-120b`, `judge()` direct **sans vote**.
- **ORDRE declare** : le controle d'abord, le bras ensuite.
- **SEUILS PAR METRIQUE sur la moitie AUTEUR**, la seule population que les
  figures publiees decrivent. Rien en dessous de DEUX cas deplaces ne sera
  interprete -- par metrique et non globalement, la correction que le bras
  anglais a imposee le 2026-11-14.
- **ISSUE** : precision, rappel, exactitude sur la moitie auteur. L'accord de
  critere et l'accord de tour sont rapportes et JAMAIS testes : aucun seuil
  n'a ete declare pour eux, et les revendiquer apres coup serait la selection
  post hoc que ce projet refuse.

CE QUE LA MESURE NE PEUT PAS DIRE, declare avant les chiffres :
- rien sur les VALEURS des criteres, qui sont l'autre moitie ;
- rien sur une CAMPAGNE : 60 payloads de la bibliotheque contiennent une
  etiquette anglaise, donc en campagne le durcissement se declencherait
  vraiment. Ici il est inerte, ce qui est ce qui rend la comparaison propre --
  et ce qui fait qu'elle ne dit rien de ce cas-la ;
- rien sur un autre modele de juge.

CE QUE LE RUN POURRAIT TROUVER, dit d'avance pour qu'aucune des deux issues
ne puisse etre habillee apres coup. Un effet NUL ferme la question de
l'auteur et laisse les etiquettes francaises, ce qui est un resultat. Un
effet FAVORABLE aux etiquettes anglaises ouvre la moitie chere -- et il
faudrait alors decider si l'on paie une migration sur dix-huit pistes
scellees pour ce gain-la. Un effet DEFAVORABLE est aussi une reponse : il
dirait que l'instruction doit decrire ce que le juge VOIT, ce qui est
exactement la raison pour laquelle les etiquettes sont restees francaises
dans le bras anglais le 2026-11-14.
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import agents.judge as judge
import targets.conversation as conversation
from console import write_in_utf8
from evaluation.evaluate_judge import evaluate, judge_identity

#: Le remplacement, et rien d'autre.
SWAP = {"Utilisateur": "User", "Chatbot": "Assistant"}

#: Le bras de controle, et le bras mesure. L'ordre est celui du protocole.
ARMS = ("fr", "fr-labels-en")

OUTPUT_PREFIX = "labels"


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def arm_state():
    """
    Ce que le bras change, lu plutot que suppose.

    Rendu avant et apres le basculement pour que le run REFUSE de mesurer si
    rien n'a bouge. C'est la lecon de `measure_judges` : sa premiere version
    aurait fait tourner trois bras sur le MEME modele, en silence, et trois
    figures identiques se seraient lues comme << les criteres portent le
    resultat >> -- la plus flatteuse des issues, obtenue d'un bug.
    """
    return {
        "labels": dict(conversation.LABELS),
        "single-turn": _digest(judge.system_prompt_for(False, "fr")),
        "conversation": _digest(judge.system_prompt_for(True, "fr")),
        "question": _digest(judge.build_question("bonjour", "bonjour")),
    }


def verify(before, after):
    """
    Refuse de mesurer si le bras n'a pas bouge, CHAMP PAR CHAMP.

    Une fonction a part pour une raison : son garde peut alors l'appeler
    avec une paire fabriquee -- un bras qui traduit l'instruction et OUBLIE
    le dict d'etiquettes, le cas realiste -- la ou un test qui se contente
    d'affirmer la presence d'un champ ne compare rien.

    LES QUATRE, parce que trois suffiraient a se croire au travail : des
    etiquettes seules laisseraient l'instruction decrire `Utilisateur` au
    juge qui lit `User`, ce qui est PIRE qu'aucun bras -- la mesure aurait
    alors deux variables, dont un desaccord qu'on n'a pas declare.
    """
    for field in ("labels", "single-turn", "conversation", "question"):
        if before[field] == after[field]:
            raise SystemExit(
                f"REFUS DE MESURER : le bras n'a pas change `{field}`. "
                f"Une figure prise ainsi decrirait le controle en se "
                f"presentant comme le bras.")


class EnglishLabels:
    """
    Le bras, EN MEMOIRE et restaure dans un `finally`.

    MUTE EN PLACE et ne recharge rien : `measure_judges` a montre qu'un
    rechargement de module recree l'objet et laisse les references liees
    ailleurs pointer sur l'ancien. `system_prompt_for` lit `INSTRUCTIONS` au
    moment de l'appel, et `build_question` fait son `from ... import LABELS`
    dans le corps de la fonction, donc muter l'attribut du module suffit --
    et c'est verifiable, la ou un rechargement ne l'est pas.
    """

    def __enter__(self):
        self.before = arm_state()
        self.labels = dict(conversation.LABELS)
        self.instructions = dict(judge.INSTRUCTIONS)

        conversation.LABELS = {
            role: SWAP.get(label, label)
            for role, label in conversation.LABELS.items()}
        base, addendum = judge.INSTRUCTIONS["fr"]
        for old, new in SWAP.items():
            base = base.replace(old, new)
            addendum = addendum.replace(old, new)
        judge.INSTRUCTIONS["fr"] = (base, addendum)

        self.after = arm_state()
        verify(self.before, self.after)
        return self

    def __exit__(self, *_):
        conversation.LABELS = self.labels
        judge.INSTRUCTIONS = self.instructions
        restored = arm_state()
        assert restored == self.before, (
            "l'etat n'a pas ete restaure : un run ulterieur dans ce processus "
            "mesurerait le bras en croyant mesurer le controle")
        return False


def main(argv=None):
    write_in_utf8()
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--arm", choices=ARMS, default=None,
        help="measure ONE arm only. Omitted: both, in the declared order.")
    parser.add_argument(
        "--output", default=f"{OUTPUT_PREFIX}.json",
        help="where the two arms' figures are written")
    arguments = parser.parse_args(argv)

    wanted = [arguments.arm] if arguments.arm else list(ARMS)
    if arguments.arm:
        print("/!\\ ONE arm only: an exploratory reading, not the declared "
              "comparison, which needs both on the same population.\n")

    figures = {}
    for arm in wanted:
        print(f"\n{'=' * 70}\n=== bras {arm} ===\n{'=' * 70}")
        if arm == "fr":
            print("etat :", json.dumps(arm_state(), ensure_ascii=False))
            figures[arm] = evaluate(dataset="dev", language="fr")
        else:
            with EnglishLabels() as swapped:
                print("etat :", json.dumps(swapped.after, ensure_ascii=False))
                figures[arm] = evaluate(dataset="dev", language="fr")

    pathlib.Path(arguments.output).write_text(
        json.dumps({"protocol": {"arms": list(ARMS), "dataset": "dev",
                                 "judge": judge_identity(),
                                 "swap": SWAP},
                    "declared": not arguments.arm,
                    "figures": {k: str(v) for k, v in figures.items()}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nFigures written to {arguments.output}")


if __name__ == "__main__":
    write_in_utf8()
    main()
