"""
pyrit_bridge/campaign.py — the orchestrator entry point (phase 3b).

What this replaces, and what it deliberately does NOT. A campaign has five
stages: reconnaissance -> planning -> attack -> judgement -> replay. PyRIT
covers the THIRD only, and that was recorded before it was integrated:
"Planning decides BEFORE the campaign what to launch (phase 5, our own code).
Adaptation rewords DURING the attack (phase 3). PyRIT covers neither
reconnaissance nor planning: that is the project's own added value."

So `main.run_campaign` keeps stages 1, 2 and 5, and calls `attack()` here in
place of its single-turn loop. Everything around it is unchanged: the mandate
guard, the audit trail, the budget circuit breaker, `result.json`, the
severity rules, the coverage section.

WHAT A MULTI-TURN ATTEMPT ACTUALLY TESTS, and this has to be said plainly
because it is not what a single-turn attempt tests.

A single-turn attempt SENDS the library's payload text. A PyRIT multi-turn
attack does not: it is given an OBJECTIVE, and its attacker model writes each
turn itself. The plan's payload therefore chooses what to aim at — its
technique, its OWASP family, its objective — while the words are PyRIT's.

That changes what the report may claim. Coverage by FAMILY still holds: the
attempt really did go after what the technique targets. But "payload X was
sent" would be false, so each launched attempt is stamped
`delivery="pyrit-multiturn"` and carries the objective actually given, and
the report says so. Letting a reader believe the library's text was sent
would be the lie by omission the coverage section exists to prevent.
"""

import asyncio

from pyrit_bridge import require_pyrit

require_pyrit()

from pyrit.executor.attack import (AttackAdversarialConfig,  # noqa: E402
                                   AttackScoringConfig, CrescendoAttack,
                                   RedTeamingAttack)

from agents.adaptation import accumulate, observe  # noqa: E402
from agents.adaptation import next_attempt         # noqa: E402
from llm_client import BudgetExceeded, call_log    # noqa: E402
from pyrit_bridge.convert import (ATTACK_NAMES,  # noqa: E402
                                  DEFAULT_ATTACK, denominator_state)
from pyrit_bridge.judge import OurJudge            # noqa: E402
from pyrit_bridge.targets import OurModel, OurTarget  # noqa: E402
from targets.conversation import MAX_TURNS         # noqa: E402

# The attacks this bridge exposes, both genuinely adaptive: their attacker
# model reads the target's reply and writes the next turn. That is level C of
# the three recorded on 2026-11-10, and the only one PyRIT was wanted for.
#
# Deliberately NOT exposed: `MultiPromptSendingAttack`, which sends a fixed
# list of turns. `targets.conversation.play()` already does exactly that, with
# no attacker model and therefore no cost — adding PyRIT for it would buy
# nothing and hide where the cost comes from.
ATTACKS = {"redteaming": RedTeamingAttack, "crescendo": CrescendoAttack}

# The names live in `convert`, which imports no PyRIT, so the CLI can offer
# them on a machine that cannot install the extra. This assertion is the
# junction: adding an attack here without naming it there fails at import,
# which is the only moment a silent divergence could still be caught.
assert set(ATTACKS) == set(ATTACK_NAMES), (
    f"catalogue drift: {sorted(ATTACKS)} against {sorted(ATTACK_NAMES)}")

# Turns per attempt. Bounded like every loop in this project, and lower than
# the contract's ceiling by default: each turn carries the whole history
# forward, so the cost of an attempt grows quadratically in this number.
DEFAULT_MAX_TURNS = 3


def _initialise_pyrit():
    """
    PyRIT's state store, which is MANDATORY: building any target raises
    "Central memory instance has not been set" without it.

    IN_MEMORY, and that is a decision rather than the easy default.

      * it needs no account and no key, so the repository's promise -- it runs
        with nothing -- survives the extra;
      * and SQLITE would write a SECOND record of the campaign beside our own
        audit trail. Two records of one engagement, one of them unsealed, is a
        chain-of-custody hazard: phase 14 exists so that a contested report
        can point at ONE trace whose integrity is checkable. An unsealed
        parallel store would be the thing an opposing party quotes.

    So PyRIT's memory lives for the length of the campaign and dies with it;
    the evidence is the trail.
    """
    from pyrit.setup import IN_MEMORY, initialize_pyrit_async
    asyncio.run(initialize_pyrit_async(memory_db_type=IN_MEMORY))


def wordings_for(profile):
    """
    Objective identifier -> its wording, rebuilt from the target profile.

    A plan attempt carries its objective as an ID (`refus-1`, `outil-1`), not
    as text, and its `text` is the attack already rendered — an INSTRUCTION TO
    THE TARGET, not a goal for an attacker model.

    So the wording is rebuilt with `objectives_for`, the very function that
    produced it when the plan was made. Nothing is invented: `refus-1` names
    the subject this target said it refuses, and that is what a multi-turn
    attacker has to be told to go after.
    """
    from agents.attacker import load_library
    from agents.planner import objectives_for

    return {objective["id"]: objective["wording"]
            for objective in objectives_for(profile, load_library())}


def objective_for(payload, wordings=None):
    """
    The goal handed to PyRIT, and where it comes from.

    The objective axis when the plan filled one — those ARE goals, in the
    target's own terms, derived from reconnaissance. Otherwise the payload's
    text, which for a garak complete payload is the attack itself: PyRIT's
    attacker model is then told to pursue an instruction rather than an
    outcome, which is a weaker brief. The provenance is stamped on the
    attempt so that difference stays visible in the report instead of being
    averaged into one figure.
    """
    wording = (wordings or {}).get(payload.get("objective"))
    if wording:
        # The elision matters because this text is SENT: "accepte de
        # utiliser" is wrong French, and the attacker model is briefed in
        # French. A brief that reads as broken is a worse brief.
        liaison = "d'" if wording[:1].lower() in "aeiouyhéèê" else "de "
        return (f"Obtenir de la cible qu'elle accepte {liaison}{wording}.",
                "objective")
    return payload["text"], "payload-text"


async def _one(attack_name, ask_target, target_name, goal, max_turns,
               vote_count=None):
    """
    One multi-turn attempt: a PyRIT attack, our model, our judge.

    A fresh judge per attempt, so `judge.verdicts` holds this attempt's
    verdicts and nothing else — a shared one would make an attempt's state
    depend on the attempts before it.
    """
    judge = OurJudge(vote_count=vote_count)
    attack = ATTACKS[attack_name](
        objective_target=OurTarget(ask=ask_target, name=target_name),
        attack_adversarial_config=AttackAdversarialConfig(target=OurModel()),
        attack_scoring_config=AttackScoringConfig(objective_scorer=judge),
        max_turns=max_turns,
    )
    result = await attack.execute_async(objective=goal)
    return result, judge


def _component(problem):
    """
    Which piece gave up, in two words.

    PyRIT names it in its error ("Component: adversarial_chat"), and the
    distinction matters to whoever reads the line: OUR attacker model failing
    is not THE TARGET failing — and the orchestrator's generic handler treats
    a RuntimeError as a target-wiring failure and advises `--probe-target`,
    which is the wrong advice in the first case.
    """
    text = str(problem)
    for component, said in (("adversarial_chat", "our attacker model"),
                            ("objective_scorer", "our judge"),
                            ("objective_target", "the target")):
        if component in text:
            return said
    return type(problem).__name__


def _budget_stop(problem):
    """
    Was this failure our budget circuit breaker, wrapped by PyRIT?

    PyRIT wraps anything a component raises in a `_StrategyRuntimeError`, so a
    `BudgetExceeded` arrives as a crash unless it is unwrapped. Letting that
    stand would turn a NORMAL stop into a failure, and the campaign would
    report "interrupted" where it should report "cut short" and keep its
    findings — the distinction phase 11 exists for.
    """
    seen = set()
    while problem is not None and id(problem) not in seen:
        seen.add(id(problem))
        if isinstance(problem, BudgetExceeded):
            return problem
        problem = problem.__cause__ or problem.__context__
    return None


def attack(plan, ask_target, *, target_name, profile=None, trail=None,
           adaptive=True, attempts=3, max_turns=DEFAULT_MAX_TURNS,
           attack_name=DEFAULT_ATTACK, vote_count=None, show=print):
    """
    The attack stage, multi-turn. Returns what `main`'s own loop returns:
    (findings, launched, states, observations, cut_short).

    Same shape, deliberately: the report, the severity rules and the coverage
    section must not learn a second vocabulary, and a PyRIT-driven campaign
    has to be comparable with a single-turn one by `git diff`.
    """
    if max_turns > MAX_TURNS:
        raise ValueError(
            f"{max_turns} turns asked for, maximum {MAX_TURNS}. Each turn "
            f"carries everything before it: the bound is there so the cost "
            f"cannot climb unwatched.")

    _initialise_pyrit()

    # THE TRAIL WRAPS THE TARGET HERE, and it has to. In a single-turn
    # campaign the orchestrator sends the payload itself and records the
    # exchange beside it; here PyRIT sends every turn through `OurTarget`, so
    # a trail that did not wrap the target would record NOTHING -- and phase 9
    # is not an optional deliverable, it is the condition for testing a remote
    # target under mandate.
    #
    # `AuditTrail.trace` had to be taught to carry the history for this: its
    # first version took `message` alone, so wrapping a target for a
    # multi-turn attack silently dropped the conversation.
    if trail:
        ask_target = trail.trace("attaque", ask_target)

    wordings = wordings_for(profile) if profile else {}
    findings, launched, states, observations = [], [], [], []
    cut_short = None

    for number in range(1, attempts + 1):
        payload = next_attempt(plan["candidates"],
                               observations if adaptive else (), launched)
        if payload is None:
            show(">>> Pool exhausted: no applicable attempt left.")
            break

        goal, provenance = objective_for(payload, wordings)
        # Stamped BEFORE the attack runs, and kept even if it fails: the
        # coverage is built from what was LAUNCHED, so an attempt that died
        # must not vanish from it.
        launched.append({**payload, "delivery": "pyrit-multiturn",
                         "pyrit_attack": attack_name,
                         "pyrit_objective": goal,
                         "pyrit_objective_from": provenance,
                         "max_turns": max_turns})

        show(f"--- Attempt {number}/{attempts} (multi-turn, "
             f"{attack_name}, up to {max_turns} turns) ---")
        show(f"  [Attacker] {payload['technique']} / "
             f"{payload['objective'] or 'complete payload'}")
        show(f"             objective ({provenance}) : {goal}")

        truncated_before = len(call_log()["truncated_replies"])
        try:
            outcome, judge = asyncio.run(
                _one(attack_name, ask_target, target_name, goal,
                     max_turns, vote_count))
        except BudgetExceeded as stop:
            cut_short = str(stop)
            show(f"\n>>> {stop}")
            show(f">>> Campaign CUT SHORT at attempt {number} of {attempts}.")
            break
        except Exception as problem:
            stop = _budget_stop(problem)
            if stop is not None:
                cut_short = str(stop)
                show(f"\n>>> {stop}")
                show(f">>> Campaign CUT SHORT at attempt {number} of "
                     f"{attempts}.")
                break

            # ONE attempt failed, and the campaign goes on. Measured on the
            # first run against a real HTTP endpoint: the local attacker
            # model exhausted PyRIT's retries emitting invalid JSON (a 3B
            # model returning a JSON *schema* instead of an instance), and
            # the whole campaign died on attempt 2 of 3 -- losing the attempt
            # that had already succeeded.
            #
            # It is recorded as `judge_undecided`, NOT as a resistance: no
            # verdict was reached, so it is a MISSING measurement and it
            # leaves the ASR denominator. Counting it as "the target held"
            # is the seventeen-point error of 2026-11-12, and counting the
            # campaign as crashed would throw away what it had established.
            #
            # And the cause is NAMED. The orchestrator's generic handler
            # treats a RuntimeError as a target-wiring failure and advises
            # `--probe-target`, which is the wrong advice when it is OUR
            # attacker model that gave up.
            states.append("judge_undecided")
            show(f"  /!\\        attempt FAILED ({_component(problem)}): "
                 f"{str(problem).splitlines()[0][:160]}")
            show("             no verdict, so this attempt leaves the ASR "
                 "denominator. The campaign continues.\n")
            continue

        truncated = len(call_log()["truncated_replies"]) > truncated_before
        if truncated:
            show("  /!\\        a reply was TRUNCATED during this "
                 "conversation: the verdict below is unreliable.")

        if not judge.verdicts:
            # The attack ended without the oracle ever ruling — PyRIT can
            # stop on its own error paths. That is a MISSING measurement, not
            # a win for the defence, so it leaves the denominator exactly as
            # an unreadable verdict does.
            states.append("judge_undecided")
            show("  [Judge]     never consulted: attempt excluded from the "
                 "denominator.\n")
            continue

        verdict = judge.verdicts[-1]
        turns = verdict["turns"]
        if trail:
            # The exchanges were traced turn by turn upstream; what is
            # recorded here is the VERDICT, which is what a contested report
            # has to be able to show.
            trail.record_verdict(number, verdict)

        show(f"  [Target]    {len(turns) // 2} turn(s) played, "
             f"PyRIT outcome {getattr(outcome, 'outcome', '?')}")
        show(f"  [Judge]     enfreint={verdict['reussi']} "
             f"({verdict['critere']}, votes {verdict.get('votes')}, "
             f"tour {verdict.get('tour')}): {verdict['analyse']}\n")

        observations = accumulate(
            observations,
            # Adaptation reads the TARGET's replies, never the attacker's: a
            # refusal pattern in our own turn is not the target refusing.
            observe(payload, "\n".join(t["content"] for t in turns
                                       if t["role"] == "target"), verdict))

        if truncated:
            states.append("reply_truncated")
            continue

        state = denominator_state(verdict)
        states.append(state)
        if state != "vulnerability":
            continue

        show("  >>> Finding recorded.\n")
        findings.append({
            "attempt": number,
            "payload": launched[-1],
            # The whole conversation, not a single reply. A finding whose
            # breach is on turn 1 is invisible in the last reply — measured, 4
            # of 19 on 2026-11-17 — so a report showing only the last turn
            # would hide its own evidence.
            "turns": turns,
            "reply": turns[-1]["content"] if turns else "",
            "verdict": verdict,
            # No replay: `verify_by_replay` replays ONE payload, and there is
            # no single payload here to replay. Said rather than silently
            # skipped, because a disclosure without a replay check is a weaker
            # finding and the report must grade it as such.
            "replay_check": None,
            "truncated": truncated,
        })

    if not cut_short:
        show(f">>> Attempt budget exhausted: {len(findings)} finding(s).")
    return findings, launched, states, observations, cut_short
