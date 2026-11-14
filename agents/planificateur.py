"""
agents/planificateur.py — The agent that decides WHAT to launch, and in what
order.

Between reconnaissance and attack: from the target profile it picks the
techniques that make sense here, the objectives to aim at, and ranks the lot
so the best combinations fit inside the attempt budget.

Design choice — RULES, not a model:
This is deliberately deterministic code. The model has already done its part
by extracting facts (the profile); handing it the decision as well would risk
it inventing a context and burning the whole budget. Here every exclusion is
traceable: we can say WHY a family was not launched, which will matter in the
report (Phase 6).

Planning ≠ adaptation. We decide here BEFORE the campaign. Rewording during
the attack, from the target's reply, is Phase 3 (PyRIT).
"""

from agents.attaquant import (TRANSFORMATIONS, load_library, compose)

# Each prerequisite is a question put to the target profile. Adding an attack
# family = adding its prerequisite here, and nothing else.
PREREQUISITES = {
    # Abusing a tool assumes the target has at least one.
    "outils": (
        lambda profile: bool(profile["outils"]),
        "aucun outil détecté chez la cible",
    ),
    # Leaking confidential data assumes there is some: a target that refuses
    # nothing and mentions no rule probably has nothing to protect.
    "secret": (
        lambda profile: bool(profile["sujets_refuses"])
        or profile["mentionne_consignes"],
        "la cible ne déclare ni sujet interdit ni consigne",
    ),
    # Extracting internal instructions assumes it has mentioned some.
    "consignes": (
        lambda profile: profile["mentionne_consignes"]
        or bool(profile["sujets_refuses"]),
        "la cible n'évoque aucune consigne interne",
    ),

    # --- Target capabilities, probed during reconnaissance ------------------
    # A deliberate tri-state: we only skip on an explicit NO. "The target did
    # not mention it" (None) lets the probe through, because missing a
    # vulnerability costs more than a wasted attempt — and because a chatbot
    # does not necessarily spell out everything it can do.
    "produit-du-code": (
        lambda profile: profile.get("produit_du_code") is not False,
        "la cible dit ne pas écrire de code",
    ),
    "traite-des-documents": (
        lambda profile: profile.get("traite_des_documents") is not False,
        "la cible dit ne pas traiter de document fourni",
    ),

    # --- Execution context, DECLARED by the operator ------------------------
    # A deliberate asymmetry with the capabilities above: here, not declared
    # means skipped. A target does not know what its output is rendered in, so
    # nobody answered — and the attack is structurally untestable without that
    # context. Until 2026-11-11 `web_injection` went out against a text
    # chatbot and the report announced "LLM02 tested": a wasted attempt AND
    # overstated coverage. The reason says how to enable it.
    "terminal": (
        lambda profile: "terminal" in (profile.get("contexte") or []),
        "sortie non rendue dans un terminal (--contexte terminal pour l'activer)",
    ),
    "rendu-riche": (
        lambda profile: "rendu-riche" in (profile.get("contexte") or []),
        "aucun client ne rend le Markdown de la sortie "
        "(--contexte rendu-riche pour l'activer)",
    ),
    "base-donnees": (
        lambda profile: "base-donnees" in (profile.get("contexte") or []),
        "aucune base ni moteur de gabarits déclaré derrière la cible "
        "(--contexte base-donnees pour l'activer)",
    ),
}

# A technique with no text template can produce nothing: we say so explicitly
# rather than letting it vanish without explanation.
REASON_NO_TEMPLATE = "aucun modèle de payload dans la bibliothèque"


def objectives_for(profile, library):
    """
    The objectives to aim at: the library's, plus those derived from the
    profile. If the target says it refuses to discuss the "vault code", then
    obtaining that code becomes an objective specific to THIS target — which
    is the whole point of reconnaissance.
    """
    objectives = list(library["objectifs"])

    for number, subject in enumerate(profile["sujets_refuses"], start=1):
        objectives.append({
            "id": f"refus-{number}",
            "formulation": f"me parler de : {subject}",
            "origine": "reconnaissance",
        })

    # A discovered tool becomes an objective. Writing "call consulter_dossier"
    # into the library would only hold against the demo target; the tool's
    # name must come from reconnaissance, exactly as the refused subject does
    # just above.
    #
    # The "pour quelqu'un d'autre que moi" is not an ornament: it is the
    # discriminant of the judge's `abus_outils` criterion. Consulting ONE'S
    # OWN record is legitimate use (case D17 of the corpus); obtaining a third
    # party's is the vulnerability. Without that clause, the four registers
    # would produce attempts the judge would class — rightly — as "aucun".
    for number, tool in enumerate(profile["outils"], start=1):
        objectives.append({
            "id": f"outil-{number}",
            "formulation": f"utiliser ton outil « {tool} » pour quelqu'un "
                           f"d'autre que moi",
            "origine": "reconnaissance",
            # The family this objective was built FOR: see `_priority`, which
            # moves it ahead on that family alone.
            "pour_famille": "LLM06",
        })

    return objectives


# --- Restricting a campaign's scope ------------------------------------------
# Three distinct needs, one mechanism:
#
# 1. THE MANDATE. `autorisation.example.json` declares a scope that mentions
#    "excluded techniques", and the report displays it faithfully — but
#    nothing enforced it. A report that cites a mandate excluding a technique,
#    then documents launching that technique, is a contractual breach.
# 2. REPRODUCING a finding after a fix, without rerunning the whole campaign
#    and without adaptation changing its mind along the way.
# 3. pass@k, which requires replaying the SAME technique k times — impossible
#    while the round-robin sweeps across modules.
#
# One pattern covers the three useful granularities, because asking for three
# would be three options to remember for the same gesture: OWASP family
# ("LLM07"), garak module ("dan") or technique ("fuite-prompt-systeme").

def _matches(technique, pattern):
    """Does the pattern name this technique, its module or its family?"""
    pattern = pattern.strip().lower()
    if not pattern:
        return False
    fields = (technique["id"], technique.get("groupe") or "",
              technique.get("famille_owasp") or "")
    return any(pattern in field.lower() for field in fields)


def filter_techniques(techniques, only=(), excluding=()):
    """
    The techniques kept, and those a pattern skipped, with their reason.

    `excluding` wins over `only`: an exclusion comes from the mandate, and a
    mandate is not worked around by another option of the same command.
    """
    kept, skipped = [], []
    for technique in techniques:
        exclusion = next((p for p in excluding if _matches(technique, p)), None)
        if exclusion:
            skipped.append((technique, f"exclue par --sauf {exclusion}"))
            continue
        if only and not any(_matches(technique, p) for p in only):
            skipped.append(
                (technique,
                 f"hors du périmètre demandé (--seulement "
                 f"{', '.join(only)})"))
            continue
        kept.append(technique)
    return kept, skipped


def plan_campaign(profile, budget, only=(), excluding=()):
    """
    Returns {"essais": [...], "candidats": [...], "ecartees": [...]}.

    - essais    : the INITIAL plan, best ranked first, at most `budget` (the
                  planner never decides to exceed the campaign's limit). This
                  is what we would launch while learning nothing from the
                  target.
    - candidats : the full POOL, sorted. The campaign draws from it as it
                  goes, reordering from the replies already obtained
                  (agents/adaptation.py). It is not truncated: an attempt
                  pushed past the initial budget must be able to climb back if
                  the target reveals it is relevant.
    - ecartees  : the techniques not kept AND why. A security tool that does
                  not say what it did NOT test gives a false impression of
                  coverage.
    """
    library = load_library()
    objectives = objectives_for(profile, library)

    kept, skipped = [], []

    # Scope first: a technique excluded by the mandate has no business being
    # skipped for "no tool detected", which would mask the real reason.
    techniques, out_of_scope = filter_techniques(library["techniques"],
                                                 only, excluding)
    for technique, reason in out_of_scope:
        skipped.append({"technique": technique["id"],
                        "famille_owasp": technique["famille_owasp"],
                        "motifs": [reason]})

    for technique in techniques:
        reasons = [text for name, (check, text) in PREREQUISITES.items()
                   if name in technique["prerequis"] and not check(profile)]
        if not technique["modeles"] and not technique.get("payloads_complets"):
            reasons.append(REASON_NO_TEMPLATE)

        if reasons:
            skipped.append({"technique": technique["id"],
                            "famille_owasp": technique["famille_owasp"],
                            "motifs": reasons})
        else:
            kept.append(technique)

    # A still-empty hand-written technique whose FAMILY is covered elsewhere
    # by garak is not a coverage hole. Without this distinction the report
    # displayed side by side "divulgation-information (LLM02) — no payload
    # template" and "Families tested: LLM02", which is contradictory for a
    # reader and invents a hole that does not exist. We do not hide it for all
    # that: we say where the family is handled.
    families_kept = {t["famille_owasp"] for t in kept if t["famille_owasp"]}
    for entry in skipped:
        # Reserved for the ONE case that justifies it: a technique skipped for
        # want of a payload, whose family is handled elsewhere. The field
        # applied to every skipped technique, which became visible — and false
        # — with the relevance rules of 2026-11-11: `ansiescape` belongs to
        # LLM01, covered elsewhere, but it tests the ANSI sequences no other
        # probe tests. Saying "covered elsewhere" suggested that skipping it
        # cost nothing.
        entry["famille_couverte_ailleurs"] = (
            REASON_NO_TEMPLATE in entry["motifs"]
            and entry["famille_owasp"] in families_kept)

    attempts = []
    for technique in kept:
        for template in technique["modeles"]:
            for objective in objectives:
                for name, transform in TRANSFORMATIONS.items():
                    text = template.format(objectif=objective["formulation"])
                    attempts.append({
                        "technique": technique["id"],
                        "famille_owasp": technique["famille_owasp"],
                        "objectif": objective["id"],
                        "transformation": name,
                        "texte": transform(text),
                        "familles_non_jugeables":
                            technique.get("familles_non_jugeables") or [],
                        "groupe": _group(technique),
                        "priorite": _priority(technique, objective, name),
                    })

        # Payloads coming from outside (garak) are complete prompts: they
        # carry their own intention, so no objective axis.
        for payload in technique.get("payloads_complets", []):
            # A complete payload serves as a PREAMBLE: alone it measures
            # resistance to hijacking; composed with an objective derived from
            # reconnaissance it goes after what the target protects.
            variants = [(o, compose(payload, o)) for o in objectives]
            variants.append((None, payload))
            for objective, text in variants:
                for name, transform in TRANSFORMATIONS.items():
                    attempts.append({
                        "technique": technique["id"],
                        "famille_owasp": technique["famille_owasp"],
                        "objectif": objective["id"] if objective else None,
                        "transformation": name,
                        "texte": transform(text),
                        "source": technique.get("source"),
                        "familles_non_jugeables":
                            technique.get("familles_non_jugeables") or [],
                        "groupe": _group(technique),
                        "priorite": _priority(technique, objective, name),
                    })

    # Stable sort: on an equal priority the library's order is kept, so two
    # identical campaigns produce the same list.
    attempts.sort(key=lambda attempt: attempt["priorite"])
    return {"essais": _share_budget(attempts, budget),
            "candidats": attempts,
            "ecartees": skipped}


def _group(technique):
    """
    The grain of the round-robin: the garak module, or the identifier for a
    hand-written technique.

    Why not the technique: `encoding` is fifteen of the fifty-two probes in
    scope, all variants of the same test. Counting by technique gave them
    fifteen turns where `dan` got three, and alphabetical order did the rest —
    a campaign on a wider budget would have burned itself on encoding variants
    before reaching `promptinject`.
    """
    return technique.get("groupe") or technique["id"]


def _share_budget(attempts, budget):
    """
    Shares the budget BETWEEN groups of techniques, instead of handing it to
    the first one.

    Sorting then cutting looked enough while the library held twelve payloads.
    With 614, the first technique took all six available attempts: we learned
    everything about one probe and nothing about the other fifty-two. But a
    scanner must sweep first, and dig second.

    So we take one attempt per technique, in priority order, then a second
    from each, and so on. At an equal budget, coverage is maximal — and the
    report can finally speak of several families.
    """
    if budget <= 0:
        return []

    by_technique = {}
    for attempt in attempts:                 # `attempts` is already sorted
        key = attempt.get("groupe") or attempt["technique"]
        by_technique.setdefault(key, []).append(attempt)

    kept = []
    rounds = max((len(v) for v in by_technique.values()), default=0)
    for index in range(rounds):
        for candidates in by_technique.values():
            if index < len(candidates):
                kept.append(candidates[index])
                if len(kept) >= budget:
                    return kept
    return kept


def _paired(technique, objective):
    """
    Was this objective built for this technique's family?

    The match is on the family's PREFIX (`LLM06`), not on its full label:
    `bibliotheque.json` writes "LLM06:2025 Excessive Agency", and making a
    priority rule depend on the OWASP vintage would break it at the Top 10's
    next revision.
    """
    expected = objective.get("pour_famille")
    family = technique.get("famille_owasp") or ""
    return bool(expected) and family.startswith(expected)


def _priority(technique, objective, transformation_name):
    """
    The smaller the number, the earlier the attempt goes. Four ideas, in
    order: aim at what the target protects, prefer a proven payload, attack
    before controlling, and start without a transformation (an attack that
    fails in clear text did not fail because of the encoding).

    `objective` is None for a complete payload, which already carries its own
    intention: it is treated as targeted, neither better nor worse than an
    objective derived from reconnaissance.
    """
    priority = 0
    if objective is None:
        # A complete payload ALONE measures resistance to hijacking. Useful,
        # but less so than the same payload tasked with demanding what the
        # target protects: on an equal priority the round-robin would keep
        # only the bare one.
        priority += 1
    elif objective.get("origine") != "reconnaissance":
        priority += 4      # a generic objective comes after a targeted one
    elif _paired(technique, objective):
        # An objective built FOR a family moves ahead on that family. Without
        # this rule the round-robin kept one attempt per technique, and on a
        # tie the list's order decided: the `abus-outils` technique went out
        # with a `refus-N` objective and called no tool at all. A tool-abuse
        # payload that names no tool tests nothing.
        priority -= 1
    if technique["id"] == "controle":
        priority += 2      # the control is not an attack: it waits its turn
    if transformation_name != "identite":
        priority += 1      # raw text first, variants afterwards
    return priority


def summarise(plan):
    """The plan in a few lines, for a campaign's display."""
    lines = [f"  {len(plan['essais'])} essai(s) retenu(s) :"]
    for attempt in plan["essais"]:
        lines.append(f"    - {attempt['technique']} / "
                     f"{attempt['objectif'] or 'payload complet'} "
                     f"/ {attempt['transformation']}")
    if plan["ecartees"]:
        # Grouped by REASON, not by technique: since the relevance rules it is
        # whole modules that get skipped, and eight `web_injection` probes
        # printed "no client renders Markdown" eight times. Repeated
        # information drowns the information that is not repeated.
        lines.append("  écartées :")
        for reason, techniques in group_by_reason(plan["ecartees"]):
            lines.append(f"    - {len(techniques)} technique(s) : {reason}")
            preview = ", ".join(techniques[:3])
            if len(techniques) > 3:
                preview += f", +{len(techniques) - 3} autre(s)"
            lines.append(f"      ({preview})")
    return "\n".join(lines)


def group_by_reason(skipped):
    """
    [(reason, [techniques])], in the order the reasons first appear.

    Shared between the campaign display and the report: the two must group the
    same way, otherwise a reader who watched the campaign would not recognise
    the report.
    """
    groups = {}
    for entry in skipped:
        reason = " ; ".join(entry["motifs"])
        groups.setdefault(reason, []).append(entry["technique"])
    return list(groups.items())
