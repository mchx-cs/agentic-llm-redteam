"""
Quelle part des figures publiées est le CRITÈRE, et quelle part le MODÈLE ?

LA QUESTION, et elle n'a jamais été posée. Tout l'édifice de mesure du projet
repose sur UN modèle chez UN fournisseur : `dev` 95 / 100 / 98 et les sept
consultations du jeu gelé sont les chiffres de `openai/gpt-oss-120b`. Le
projet le sait — `MEASURED_ON` retire la note de comparabilité dès que le juge
diffère — mais la conséquence n'a pas été tirée : **on ne sait pas si ces
chiffres décrivent nos critères ou ce modèle-là.**

Et c'est une question bon marché : un run de corpus par bras, et aucune
quantité de protocoles supplémentaires ne peut y répondre.

====================================================================
PROTOCOLE, DÉCLARÉ AVANT LE MOINDRE RUN (2026-11-26)
====================================================================

  * TROIS BRAS sur le MÊME corpus `dev`, et le troisième est ce qui rend les
    deux premiers lisibles :

        openai/gpt-oss-120b   l'incumbent, et le CONTRÔLE. Il doit reproduire
                              la figure publiée ; s'il ne la reproduit pas,
                              quelque chose a bougé entre les deux runs et
                              rien n'est comparable.
        qwen/qwen3.8-27b      une AUTRE FAMILLE. C'est la question posée.
        openai/gpt-oss-20b    la MÊME famille, une taille comparable à Qwen.

    Sans le troisième, un Qwen plus faible serait inattribuable : famille ou
    capacité ? Ce sont les seuls modèles que ce compte sert et qui soient
    utilisables comme juge — vérifié, pas supposé : les autres sont des
    modèles audio, un classifieur d'injection de 86 M de paramètres, ou
    décommissionnés.

  * LA LECTURE À TROIS, déclarée d'avance pour qu'aucune issue ne soit
    habillée après coup :

        Qwen ~ gpt-oss-20b, et les deux < 120b
            -> c'est la CAPACITÉ, pas la famille. Les figures publiées sont
               une propriété de faire tourner un grand modèle.
        Qwen < gpt-oss-20b
            -> il y a une composante de FAMILLE. L'argument de la phase 4 —
               « un juge d'une autre famille ne partage pas les angles morts
               de sa cible » — gagne alors un COÛT chiffré, qu'il n'a jamais
               eu.
        Qwen ~ 120b
            -> les CRITÈRES portent le résultat, et c'est l'affirmation la
               plus forte possible sur l'instruction : le modèle du juge
               serait remplaçable.

  * L'ISSUE : précision, rappel et exactitude sur `dev`, lues sur la MOITIÉ
    ÉTIQUETÉE PAR L'AUTEUR — la seule population que les figures publiées
    décrivent. Une figure sur des étiquettes décidées par un modèle mesure
    l'accord entre modèles, et ici elle mesurerait l'accord entre le juge
    testé et celui qui a étiqueté. Le total est rapporté à côté, jamais lu
    comme le résultat.

  * SEUILS PAR MÉTRIQUE, sur cette moitié (90 entrées, 34 positives) : un cas
    y vaut ~1,1 point d'exactitude, ~2,9 de précision et ~2,9 de rappel. Rien
    en dessous de deux cas déplacés ne sera interprété. Par métrique et non
    globalement, la correction que le bras anglais a imposée le 2026-11-14.

  * AUCUN TEST DE SIGNIFICATIVITÉ, déclaré. Les trois bras jugent les MÊMES
    entrées, donc un test apparié existe (McNemar) — et ce projet n'en a
    aucun, en inventer un pour l'occasion mettrait une statistique non
    éprouvée sous un résultat. Les figures sont rapportées avec leur seuil de
    lecture, la discipline que les sept consultations du jeu gelé emploient.

  * LE JEU GELÉ N'EST PAS CONSULTÉ, et ce n'est pas un oubli. Comparer des
    modèles de juge n'est pas un « moment clé » au sens de la règle : ce qui
    change n'est pas l'artefact mesuré, c'est l'instrument qui le lit. Le
    consulter trois fois brûlerait sa valeur de référence pour une question
    que `dev` répond.

  * LA REPRISE EST GRATUITE ET DÉJÀ CORRECTE : le cache de `resume.py`
    s'invalide sur le juge (`profil/modèle`), donc chaque bras met en cache à
    part sans qu'on ait rien à ajouter. C'est exactement la clé qui existe
    pour empêcher qu'une reprise mélange deux modèles dans un chiffre.

  * CE QUE LE RUN NE DIRA PAS : rien sur le jeu gelé, rien sur le format
    conversation (le même `--only` serait un second variable), et rien sur un
    fournisseur autre que celui-ci. Un modèle d'OpenAI par le profil `api`
    serait un quatrième bras et une autre facture ; `OPENAI_MODEL` est vide,
    donc c'est une décision de l'auteur.

====================================================================

    .venv/Scripts/python -m evaluation.measure_judges
    .venv/Scripts/python -m evaluation.measure_judges --arm qwen/qwen3.8-27b
"""

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from console import write_in_utf8                       # noqa: E402

#: Les trois bras, dans l'ordre où ils sont joués : le CONTRÔLE d'abord.
#:
#: L'incumbent en premier et non en dernier, délibérément : s'il ne reproduit
#: pas la figure publiée, rien n'est comparable et il vaut mieux l'apprendre
#: avant d'avoir payé les deux autres.
ARMS = (
    ("openai/gpt-oss-120b", "l'incumbent, le CONTRÔLE"),
    ("qwen/qwen3.8-27b", "une AUTRE famille"),
    ("openai/gpt-oss-20b", "la MÊME famille, taille comparable à Qwen"),
)

#: La figure publiée que le bras de contrôle doit reproduire, sur la moitié
#: auteur de `dev`. Figée ici : sans elle, « le contrôle a reproduit » est une
#: affirmation que personne ne peut vérifier.
PUBLISHED = {"precision": 0.92, "recall": 1.00, "accuracy": 0.97}

DATASET = "dev"
LANGUAGE = "fr"

OUTPUT_PREFIX = "judges"
OUTPUT = pathlib.Path(f"{OUTPUT_PREFIX}.json")


def departures_from_the_protocol(arms=None, dataset=DATASET,
                                 language=LANGUAGE):
    said = []
    if arms is not None and tuple(arms) != tuple(a for a, _ in ARMS):
        said.append(f"arms={list(arms)} (declared {[a for a, _ in ARMS]})")
    if dataset != DATASET:
        said.append(f"dataset={dataset} (declared {DATASET})")
    if language != LANGUAGE:
        said.append(f"language={language} (declared {LANGUAGE})")
    return said


def _one_arm(model, dataset=DATASET, language=LANGUAGE, show=print):
    """
    Un bras : le modèle du juge, puis le corpus.

    Le modèle passe par `GROQ_MODEL`, qui est le point de réglage que
    `config.py` déclare pour ça — « remplaçable par GROQ_MODEL, sans toucher
    au code ». Il est restitué ensuite, et dit à voix haute : une mesure qui
    réécrit en silence ce qu'elle mesure ne vaut rien.
    """
    import config
    import importlib

    before = os.environ.get("GROQ_MODEL")
    os.environ["GROQ_MODEL"] = model
    importlib.reload(config)
    try:
        import evaluation.evaluate_judge as evaluator
        importlib.reload(evaluator)
        show(f"  judge now: {evaluator.judge_identity()}")
        counts, metrics = evaluator.evaluate(dataset=dataset,
                                             language=language)
        return counts, metrics
    finally:
        if before is None:
            os.environ.pop("GROQ_MODEL", None)
        else:
            os.environ["GROQ_MODEL"] = before
        importlib.reload(config)


def measure(arms=None, dataset=DATASET, language=LANGUAGE, output=OUTPUT,
            show=print):
    chosen = list(arms) if arms else [model for model, _ in ARMS]
    departures = departures_from_the_protocol(arms if arms else None,
                                             dataset, language)
    if departures:
        show("/!\\ EXPLORATORY, not confirmatory: "
             + ", ".join(departures) + "\n")

    show("HOW MUCH OF THE PUBLISHED FIGURES IS THE CRITERIA, AND HOW MUCH "
         "THE MODEL?\n")
    for model, role in ARMS:
        mark = ">" if model in chosen else " "
        show(f"  {mark} {model:26} {role}")
    show(f"\n  corpus    : {dataset}, instruction {language}\n"
         f"  read on   : the AUTHOR-labelled half, the only population the\n"
         f"              published figures describe\n"
         f"  threshold : nothing below two cases moved is interpreted\n")

    done = {}
    if output.exists():
        done = json.loads(output.read_text(encoding="utf-8")).get("arms", {})
        if done:
            show(f"Resuming: {len(done)} arm(s) already on disk.\n")

    for model in chosen:
        if model in done:
            continue
        show(f"\n--- {model}")
        counts, metrics = _one_arm(model, dataset, language, show=show)
        done[model] = {"counts": counts, "metrics": metrics}
        output.write_text(json.dumps(
            {"protocol": {"dataset": dataset, "language": language,
                          "arms": [a for a, _ in ARMS],
                          "declared": not departures},
             "arms": done}, ensure_ascii=False, indent=1), encoding="utf-8")

    return done


def main(arguments=None):
    write_in_utf8()
    parser = argparse.ArgumentParser(
        description="Three judge models on one corpus.")
    parser.add_argument("--arm", action="append", dest="arms",
                        help="one arm only (repeatable); omitted = all three")
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--language", default=LANGUAGE)
    parser.add_argument("--output", default=str(OUTPUT))
    arguments = parser.parse_args(arguments)

    measure(arms=arguments.arms, dataset=arguments.dataset,
            language=arguments.language,
            output=pathlib.Path(arguments.output))
    return 0


if __name__ == "__main__":
    write_in_utf8()
    sys.exit(main())
