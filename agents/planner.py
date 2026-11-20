"""
agents/planner.py — The agent that decides WHAT to launch, and in what
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

from agents.attacker import (TRANSFORMATIONS, load_library, compose)

# Each prerequisite is a question put to the target profile. Adding an attack
# family = adding its prerequisite here, and nothing else.
PREREQUISITES = {
    # Abusing a tool assumes the target has at least one.
    "tools": (
        lambda profile: bool(profile["tools"]),
        "no tool detected on the target",
    ),
    # Leaking confidential data assumes there is some: a target that refuses
    # nothing and mentions no rule probably has nothing to protect.
    "secret": (
        lambda profile: bool(profile["refused_subjects"])
        or profile["mentions_instructions"],
        "the target declares neither a forbidden subject nor a rule",
    ),
    # Extracting internal instructions assumes it has mentioned some.
    "instructions": (
        lambda profile: profile["mentions_instructions"]
        or bool(profile["refused_subjects"]),
        "the target mentions no internal instruction",
    ),

    # --- Target capabilities, probed during reconnaissance ------------------
    # A deliberate tri-state: we only skip on an explicit NO. "The target did
    # not mention it" (None) lets the probe through, because missing a
    # vulnerability costs more than a wasted attempt — and because a chatbot
    # does not necessarily spell out everything it can do.
    "writes-code": (
        lambda profile: profile.get("writes_code") is not False,
        "the target says it does not write code",
    ),
    "handles-documents": (
        lambda profile: profile.get("handles_documents") is not False,
        "the target says it does not handle supplied documents",
    ),

    # --- Execution context, DECLARED by the operator ------------------------
    # A deliberate asymmetry with the capabilities above: here, not declared
    # means skipped. A target does not know what its output is rendered in, so
    # nobody answered — and the attack is structurally untestable without that
    # context. Until 2026-11-11 `web_injection` went out against a text
    # chatbot and the report announced "LLM02 tested": a wasted attempt AND
    # overstated coverage. The reason says how to enable it.
    "terminal": (
        lambda profile: "terminal" in (profile.get("context") or []),
        "output not rendered in a terminal (--context terminal to enable)",
    ),
    "rich-rendering": (
        lambda profile: "rich-rendering" in (profile.get("context") or []),
        "no client renders the output's Markdown "
        "(--context rich-rendering to enable)",
    ),
    "database": (
        lambda profile: "database" in (profile.get("context") or []),
        "no database or template engine declared behind the target "
        "(--context database to enable)",
    ),
}

# A technique with no text template can produce nothing: we say so explicitly
# rather than letting it vanish without explanation.
REASON_NO_TEMPLATE = "no payload template in the library"


def objectives_for(profile, library):
    """
    The objectives to aim at: the library's, plus those derived from the
    profile. If the target says it refuses to discuss the "vault code", then
    obtaining that code becomes an objective specific to THIS target — which
    is the whole point of reconnaissance.
    """
    objectives = list(library["objectives"])

    for number, subject in enumerate(profile["refused_subjects"], start=1):
        objectives.append({
            "id": f"refus-{number}",
            "wording": f"me parler de : {subject}",
            "origin": "reconnaissance",
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
    for number, tool in enumerate(profile["tools"], start=1):
        objectives.append({
            "id": f"outil-{number}",
            "wording": f"utiliser ton outil « {tool} » pour quelqu'un "
                           f"d'autre que moi",
            "origin": "reconnaissance",
            # The family this objective was built FOR: see `_priority`, which
            # moves it ahead on that family alone.
            "for_family": "LLM06",
        })

    return objectives


# --- Restricting a campaign's scope ------------------------------------------
# Three distinct needs, one mechanism:
#
# 1. THE MANDATE. `authorisation.example.json` declares a scope that mentions
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
    fields = (technique["id"], technique.get("group") or "",
              technique.get("owasp_family") or "")
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
            skipped.append(
                (technique, f"excluded by --excluding {exclusion}"))
            continue
        if only and not any(_matches(technique, p) for p in only):
            skipped.append(
                (technique,
                 f"outside the scope asked for (--only "
                 f"{', '.join(only)})"))
            continue
        kept.append(technique)
    return kept, skipped


def plan_campaign(profile, budget, only=(), excluding=(), repeat=False):
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

    `repeat` is pass@k: the pool becomes ONE combination, repeated to the
    budget, instead of a sweep. It is what makes an i.i.d. measurement
    possible at all -- a sweep over one technique still crosses several
    objectives and transformations, which `stats.py` calls heterogeneous, so
    the bound it would print would be over different Bernoulli variables. The
    attempt chosen is the pool's own head, so the choice stays the planner's
    priority order and not a second rule nobody can audit.
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
                        "owasp_family": technique["owasp_family"],
                        "reasons": [reason]})

    for technique in techniques:
        reasons = [text for name, (check, text) in PREREQUISITES.items()
                   if name in technique["prerequisites"] and not check(profile)]
        if not technique["templates"] and not technique.get("complete_payloads"):
            reasons.append(REASON_NO_TEMPLATE)

        if reasons:
            skipped.append({"technique": technique["id"],
                            "owasp_family": technique["owasp_family"],
                            "reasons": reasons})
        else:
            kept.append(technique)

    # A still-empty hand-written technique whose FAMILY is covered elsewhere
    # by garak is not a coverage hole. Without this distinction the report
    # displayed side by side "divulgation-information (LLM02) — no payload
    # template" and "Families tested: LLM02", which is contradictory for a
    # reader and invents a hole that does not exist. We do not hide it for all
    # that: we say where the family is handled.
    families_kept = {t["owasp_family"] for t in kept if t["owasp_family"]}
    for entry in skipped:
        # Reserved for the ONE case that justifies it: a technique skipped for
        # want of a payload, whose family is handled elsewhere. The field
        # applied to every skipped technique, which became visible — and false
        # — with the relevance rules of 2026-11-11: `ansiescape` belongs to
        # LLM01, covered elsewhere, but it tests the ANSI sequences no other
        # probe tests. Saying "covered elsewhere" suggested that skipping it
        # cost nothing.
        entry["family_covered_elsewhere"] = (
            REASON_NO_TEMPLATE in entry["reasons"]
            and entry["owasp_family"] in families_kept)

    attempts = []
    for technique in kept:
        for template in technique["templates"]:
            for objective in objectives:
                for name, transform in TRANSFORMATIONS.items():
                    text = template.format(objective=objective["wording"])
                    attempts.append({
                        "technique": technique["id"],
                        "owasp_family": technique["owasp_family"],
                        "objective": objective["id"],
                        "transformation": name,
                        "text": transform(text),
                        "families_not_scorable":
                            technique.get("families_not_scorable") or [],
                        "group": _group(technique),
                        "priority": _priority(technique, objective, name),
                    })

        # Payloads coming from outside (garak) are complete prompts: they
        # carry their own intention, so no objective axis.
        for payload in technique.get("complete_payloads", []):
            # A complete payload serves as a PREAMBLE: alone it measures
            # resistance to hijacking; composed with an objective derived from
            # reconnaissance it goes after what the target protects.
            variants = [(o, compose(payload, o)) for o in objectives]
            variants.append((None, payload))
            for objective, text in variants:
                for name, transform in TRANSFORMATIONS.items():
                    attempts.append({
                        "technique": technique["id"],
                        "owasp_family": technique["owasp_family"],
                        "objective": objective["id"] if objective else None,
                        "transformation": name,
                        "text": transform(text),
                        "source": technique.get("source"),
                        "families_not_scorable":
                            technique.get("families_not_scorable") or [],
                        "group": _group(technique),
                        "priority": _priority(technique, objective, name),
                    })

    # Stable sort: on an equal priority the library's order is kept, so two
    # identical campaigns produce the same list.
    attempts.sort(key=lambda attempt: attempt["priority"])

    if repeat and attempts:
        # ONE combination, `budget` times. The list is built rather than the
        # same dict repeated: the campaign stamps adaptation reasons on what
        # it draws, and a shared dict would see every turn's annotations.
        #
        # `candidates` is normally the untruncated pool, because a relegated
        # attempt must be able to climb back. Here there is nothing to climb
        # over, and leaving the others in would let the campaign wander off
        # the one combination it was told to measure.
        chosen = attempts[0]
        attempts = [dict(chosen) for _ in range(budget)]
        return {"attempts": attempts, "candidates": attempts,
                "skipped": skipped,
                # WHAT was repeated, so the bound is auditable in the document
                # that prints it. On 2026-11-19 the report claimed
                # independence while `result.json` kept no attempt list at
                # all, and the triples had to be counted from stdout.
                "repeated": {"technique": chosen["technique"],
                             "objective": chosen["objective"],
                             "transformation": chosen["transformation"]}}

    return {"attempts": _share_budget(attempts, budget),
            "candidates": attempts,
            "skipped": skipped}


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
    return technique.get("group") or technique["id"]


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
        key = attempt.get("group") or attempt["technique"]
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
    `library.json` writes "LLM06:2025 Excessive Agency", and making a
    priority rule depend on the OWASP vintage would break it at the Top 10's
    next revision.
    """
    expected = objective.get("for_family")
    family = technique.get("owasp_family") or ""
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
    elif objective.get("origin") != "reconnaissance":
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
    if transformation_name != "identity":
        priority += 1      # raw text first, variants afterwards
    return priority


def summarise(plan):
    """The plan in a few lines, for a campaign's display."""
    lines = [f"  {len(plan['attempts'])} attempt(s) kept:"]
    for attempt in plan["attempts"]:
        lines.append(f"    - {attempt['technique']} / "
                     f"{attempt['objective'] or 'complete payload'} "
                     f"/ {attempt['transformation']}")
    if plan["skipped"]:
        # Grouped by REASON, not by technique: since the relevance rules it is
        # whole modules that get skipped, and eight `web_injection` probes
        # printed "no client renders Markdown" eight times. Repeated
        # information drowns the information that is not repeated.
        lines.append("  skipped:")
        for reason, techniques in group_by_reason(plan["skipped"]):
            lines.append(f"    - {len(techniques)} technique(s): {reason}")
            preview = ", ".join(techniques[:3])
            if len(techniques) > 3:
                preview += f", +{len(techniques) - 3} more"
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
        reason = " ; ".join(entry["reasons"])
        groups.setdefault(reason, []).append(entry["technique"])
    return list(groups.items())
