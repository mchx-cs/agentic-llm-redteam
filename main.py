"""
main.py — The orchestrator: reconnaissance → planning → attack → judgement.

How a campaign runs:
  1. We OBSERVE the target (harmless questions) to build a profile.
  2. We PLAN: which families make sense here, and in what order.
  3. For each attempt kept: we send, the target answers, the judge scores.
  4. A disclosure is checked by REPLAY before being declared (a target that
     invents a password has disclosed nothing).

Two budgets, because two loops: RECON_BUDGET for observation, MAX_ESSAIS for
the attack. Without them, an adaptive agent would run for ever.

Run it with:
    python main.py                       # the target named in .env
    python main.py --cible mock          # deterministic, no model
    python main.py --cible https://...   # a real endpoint
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from audit import (AUTHORISATION_FILE, MissingAuthorisation, AuditTrail,
                   require_mandate, telemetry)
from agents.adaptation import accumulate, observe, next_attempt
from agents.arbitre import judge, judge_by_vote
from agents.planificateur import plan_campaign, summarise as summarise_plan
from agents.reconnaissance import (KNOWN_CONTEXTS, reconnoitre,
                                   summarise as summarise_profile)
from agents.verificateur import verify_by_replay
from cibles import choose_target
from cibles.http import TARGET_PROFILES, probe_target as probe_http_target
from config import CALL_BUDGET, TOKEN_BUDGET, TARGET
from llm_client import BudgetExceeded, call_log, reset_call_log
from rapport import save_report

# The stopping rule: we do not attack indefinitely.
MAX_ESSAIS = 3


def run_campaign(ask_target=None, target_name=None, trail=None,
                 context=(), adaptive=True, only=(), excluding=()):
    """
    Runs a campaign against `ask_target`.

    The target is a parameter, not an import: that is what lets us aim at a
    real endpoint, the local decoy or a simulated target without touching the
    orchestrator's code. By default, the one `.env` names.

    `trail` is an optional AuditTrail. When supplied, every exchange with the
    target is recorded in it as it goes — reconnaissance and replay included,
    since the target is wrapped upstream.
    """
    ask_target = ask_target or choose_target()
    target_name = target_name or TARGET

    print("=== Campaign ===\n")
    # The budget is armed HERE, not in llm_client: the evaluation scripts
    # consume far more than a campaign and have no reason to be cut off in
    # the middle of a measurement.
    reset_call_log(CALL_BUDGET, TOKEN_BUDGET)

    # --- 1. Reconnaissance: who is this target? ----------------------------
    print("--- Reconnaissance ---")
    try:
        profile = reconnoitre(trail.trace("reconnaissance", ask_target)
                              if trail else ask_target)
    except BudgetExceeded as stop:
        print(f"\n>>> {stop}")
        return _finish({"status": "budget_exhausted", "profile": None,
                        "plan": {"attempts": [], "candidates": [],
                                 "skipped": []},
                        "findings": [], "cut_short": str(stop)})
    # The context comes from the OPERATOR, not from a probe: a target does not
    # know what its output is rendered in, and asking it would invite
    # hallucination. So we add it afterwards, without touching the observed
    # facts.
    profile["context"] = list(context)
    print(summarise_profile(profile))

    # --- 2. Planning: what to launch, and in what order? -------------------
    print("\n--- Plan ---")
    plan = plan_campaign(profile, MAX_ESSAIS, only, excluding)
    print(summarise_plan(plan))

    if not plan["attempts"]:
        print("\n>>> No attempt applies to this target. Campaign over.")
        return _finish({"status": "no_attempt", "profile": profile,
                        "plan": plan, "findings": []})

    # --- 3. Attack ---------------------------------------------------------
    # We go to the END of the budget instead of stopping at the first
    # vulnerability: a report is only worth something if it says everything
    # that was found, and what it stayed silent about. Stopping early would
    # make any claim of coverage impossible.
    #
    # The next attempt is not read from a frozen list: it is CHOSEN each turn
    # from the planner's pool, from what the target has already replied
    # (phase 3a, agents/adaptation.py). The loop stays bounded by MAX_ESSAIS —
    # adaptation changes the order, never the number of attempts.
    findings = []
    observations = []       # what we have learned about the target, cumulated
    launched = []           # the attempts actually sent, in order
    states = []             # each one's outcome: scorable or not (ASR)
    cut_short = None
    print()
    for number in range(1, MAX_ESSAIS + 1):
        # `adaptive=False` replays the static plan: same pool, same priority
        # order, but learning nothing from the replies. That is the CONTROL
        # the gain measurement needs — without it, adaptation can only be
        # compared against simulated campaigns.
        payload = next_attempt(plan["candidates"],
                               observations if adaptive else (), launched)
        if payload is None:
            print(">>> Pool exhausted: no applicable attempt left.")
            break
        launched.append(payload)

        print(f"--- Attempt {number}/{MAX_ESSAIS} ---")
        print(f"  [Attacker] {payload['technique']} / "
              f"{payload['objective'] or 'complete payload'} "
              f"/ {payload['transformation']}")
        if payload.get("adaptation_reasons"):
            # The net first: an attempt can carry both a bonus and a penalty,
            # and without it the reasons look contradictory.
            print(f"  [Adaptation] net {payload['adaptation_score']:+d} "
                  f"on its starting priority "
                  f"({payload['priority']}):")
            for reason in payload["adaptation_reasons"]:
                print(f"               - {reason}")
        print(f"             sends : {payload['text']}")

        try:
            # A reply cut off by the target's output cap reads like a complete
            # one: the verdict would then be worth nothing.
            truncated_before = len(call_log()["truncated_replies"])
            reply = ask_target(payload["text"])
            truncated = len(call_log()["truncated_replies"]) > truncated_before
            if trail:
                trail.record_exchange("attaque", payload["text"], reply,
                                      truncated)
            print(f"  [Target]    replies : {reply}")
            if truncated:
                print("  /!\\        reply TRUNCATED: a leak may have been "
                      "cut in half, the verdict below is unreliable.")

            # Voting: the judge is not deterministic on borderline cases, and
            # a vulnerability that appears with the draw has no business in a
            # report.
            verdict = judge_by_vote(payload["text"], reply)
            if trail:
                trail.record_verdict(number, verdict)
            print(f"  [Judge]     enfreint={verdict['reussi']} "
                  f"({verdict['critere']}, votes {verdict['votes']}): "
                  f"{verdict['analyse']}\n")

            # What this exchange teaches us, for choosing the next attempt.
            # Recorded BEFORE any `continue`: a failure instructs as much as a
            # success, and that is in fact its only use.
            observations = accumulate(observations,
                                      observe(payload, reply, verdict))

            # An unreadable verdict (None) is NOT a vulnerability — but it is
            # not a win for the target either. Confusing the two inflated its
            # apparent soundness: a judge that does not decide is a MISSING
            # measurement, not a refusal. The attempt is therefore excluded
            # from the ASR denominator (OWASP manual §7.5), and counted apart.
            if truncated:
                states.append("reply_truncated")
                continue
            if verdict["reussi"] is None:
                states.append("judge_undecided")
                continue
            if verdict["reussi"] is False:
                states.append("resisted")
                continue

            # --- 4. Replay check, if a value was disclosed -----------------
            replay_check = None
            if verdict["critere"] == "divulgation":
                # The replay gets `judge` without voting: it already queries
                # the target several times, which smooths the noise. Voting on
                # top would cost nine calls where three are enough.
                replay_check = verify_by_replay(
                    payload["text"], verdict["valeur"],
                    trail.trace("rejeu", ask_target) if trail
                    else ask_target,
                    judge,
                )
                print(f"  [Replay]    {replay_check['status']}: "
                      f"{replay_check['explanation']}")

                if replay_check["status"] == "likely_hallucination":
                    # The target made it up: nothing leaked, no finding.
                    # Scorable all the same — the attack did fail, and the
                    # replay established it instead of assuming it.
                    states.append("hallucination")
                    print("  >>> Value invented by the target: moving on.\n")
                    continue
        except BudgetExceeded as stop:
            # A NORMAL stop, not a failure: we keep what has been found so
            # far, and we will say plainly that the plan did not run to its
            # end. The attempt in flight is lost, and that is accepted.
            cut_short = str(stop)
            print(f"\n>>> {stop}")
            print(f">>> Campaign CUT SHORT at attempt {number} of "
                  f"{MAX_ESSAIS}.")
            break

        print("  >>> Finding recorded.\n")
        states.append("vulnerability")
        findings.append({
            "attempt": number,
            "payload": payload,
            "reply": reply,
            "verdict": verdict,
            # None (compliance, no value), or the replay's result:
            # "confirmee", "contradictoire", "inconcluant"…
            "replay_check": replay_check,
            "truncated": truncated,
        })

    if not cut_short:
        print(f">>> Attempt budget exhausted: {len(findings)} finding(s).")

    return _finish({
        # A plan cut short must NEVER present itself as a finished plan:
        # "no finding" does not mean the same thing in the two cases.
        "status": ("budget_exhausted" if cut_short
                   else "findings" if findings else "no_finding"),
        "profile": profile,
        "plan": plan,
        "findings": findings,
        # The attempts REALLY sent, and what we learned along the way. It is
        # from these that the report draws its coverage: since adaptation, the
        # initial plan is no longer what was launched, and announcing the
        # plan's coverage would be a lie by omission.
        "launched": launched,
        "observations": observations,
        # Each attempt's outcome, so the report computes an ASR over a DEFINED
        # denominator rather than over the number of sends.
        "states": states,
        # The scope asked for: the report MUST say it, otherwise a campaign
        # restricted to one family would present its coverage as complete.
        "scope": {"only": list(only), "excluding": list(excluding)},
        # Are the attempts i.i.d.? Two conditions, both necessary: no
        # adaptation (otherwise the next one depends on the previous replies)
        # and a single technique launched (otherwise payloads from different
        # families do not share the same probability of success). When both
        # hold — typically `--seulement X --sans-adaptation` — the report can
        # finally bound its "no finding", which is precisely what pass@k asks.
        "independent_attempts": (
            not adaptive
            and len({a["technique"] for a in launched}) <= 1
            and len(launched) > 0),
        "cut_short": cut_short,
    })


def _finish(result):
    """Attaches the call log and warns if any reply was cut off."""
    result.setdefault("cut_short", None)
    result.setdefault("launched", [])
    result.setdefault("states", [])
    result.setdefault("scope", {"only": [], "excluding": []})
    result.setdefault("independent_attempts", False)
    result.setdefault("observations", [])
    result.setdefault("payloads", _payload_provenance())
    result["call_log"] = call_log()
    truncated_count = len(result["call_log"]["truncated_replies"])

    print(f"\n{result['call_log']['calls']} call(s) to the model, "
          f"{result['call_log']['tokens']} tokens.")
    if truncated_count:
        # A "no vulnerability" obtained on cut-off replies is worth nothing:
        # say so plainly rather than letting it look like coverage.
        print(f"/!\\ {truncated_count} truncated reply/replies: the matching "
              f"verdicts are unreliable, and a \"no vulnerability\" could be "
              f"hiding a leak cut in half.")
    return result


def _payload_provenance():
    """Which library the campaign worked with, and how old it is."""
    from agents.attaquant import SNAPSHOT_AGE_SUSPECT, load_library

    garak = load_library().get("_garak")
    if not garak:
        return None
    age = garak.get("age_days")
    return {**garak,
            "stale": age is not None and age > SNAPSHOT_AGE_SUSPECT}


def scope_patterns(value):
    """Splits "dan, encoding" into clean patterns, no blanks, no duplicates."""
    seen, patterns = set(), []
    for pattern in (value or "").split(","):
        pattern = pattern.strip()
        if pattern and pattern.lower() not in seen:
            seen.add(pattern.lower())
            patterns.append(pattern)
    return patterns


def cli(arguments=None):
    """Command-line entry point (see [project.scripts])."""
    parser = argparse.ArgumentParser(description="Runs a test campaign.")
    # Every option keeps its French name as an alias: the README has shown
    # `--cible demo` since the project existed, and a documented interface
    # does not get pulled from under its users by a translation. argparse
    # takes its destination from the FIRST long option, so the code reads the
    # English name.
    parser.add_argument(
        "--target", "--cible", default=None, dest="target",
        help="'leurre' (default), 'mock', or an http(s) URL. Otherwise the "
             "value of CIBLE in .env.")
    parser.add_argument(
        "--report", "--rapport", nargs="?", const="rapports", default=None,
        dest="report", metavar="FOLDER",
        help="write resultat.json and rapport.md into FOLDER "
             "(default: rapports/).")
    parser.add_argument(
        "--abridge", "--abreger", action="store_true", dest="abridge",
        help="truncate payloads and replies in rapport.md (to share a report "
             "without a client's verbatim replies, or to publish an "
             "example). resultat.json keeps everything.")
    parser.add_argument(
        "--only", "--seulement", default="", dest="only", metavar="PATTERNS",
        help="restrict the campaign, by OWASP family (LLM07), garak module "
             "(dan) or technique (fuite-prompt-systeme); several patterns "
             "separated by commas. The report always says the campaign was "
             "restricted.")
    parser.add_argument(
        "--excluding", "--sauf", default="", dest="excluding",
        metavar="PATTERNS",
        help="skip techniques, same patterns as --only. Serves to respect a "
             "mandate scope that excludes techniques; wins over --only.")
    parser.add_argument(
        "--no-adaptation", "--sans-adaptation", action="store_true",
        dest="no_adaptation",
        help="follow the static plan, learning nothing from the replies. "
             "Serves as the control for measuring what adaptation adds; of "
             "no use in normal operation.")
    parser.add_argument(
        "--target-profile", "--profil-cible", default=None, metavar="NAME",
        dest="target_profile",
        help="the target's API shape, instead of describing TARGET_BODY and "
             "TARGET_RESPONSE_PATH by hand: "
             + ", ".join(TARGET_PROFILES)
             + ". Wins over TARGET_BODY and TARGET_RESPONSE_PATH from .env: "
               "the command line is more specific. For a bespoke body, set "
               ".env and pass no profile.")
    parser.add_argument(
        "--probe-target", "--tester-cible", action="store_true",
        dest="probe_target",
        help="send ONE harmless message to check the wiring, then stop. No "
             "attack, no mandate required: to be run before any campaign "
             "against a real target.")
    parser.add_argument(
        "--context", "--contexte", default="", dest="context",
        metavar="LIST",
        help="what the application AROUND the target does with its output, "
             "comma-separated: "
             + ", ".join(KNOWN_CONTEXTS)
             + ". Some probe families make no sense without this, and a "
               "target cannot declare it itself.")
    parser.add_argument(
        "--authorisation", "--autorisation", default=AUTHORISATION_FILE,
        dest="authorisation", metavar="FILE",
        help=f"mandate covering the target (default: {AUTHORISATION_FILE}). "
             f"Not needed for a local target.")
    arguments = parser.parse_args(arguments)

    target_name = arguments.target or TARGET

    # The target's NAME first, and this is a correction: a typo ("demo:9",
    # "leure") used to come out either as a Python traceback or — worse — as
    # an authorisation message, which talked about a mandate to someone who
    # had simply mistyped a letter. So we check the name before anything,
    # which sends no request and does not disturb the mandate's order.
    try:
        choose_target(target_name, arguments.target_profile)
    except (ValueError, RuntimeError) as refusal:
        print(f"Target unusable.\n{refusal}", file=sys.stderr)
        raise SystemExit(2)

    # An unknown context name is a TYPO, not an absent context: accepting it
    # silently would skip whole families without anyone understanding why.
    # Same logic as an unknown profile, which fails at import with the list of
    # valid values.
    context = [c.strip() for c in arguments.context.split(",") if c.strip()]
    unknown = [c for c in context if c not in KNOWN_CONTEXTS]
    if unknown:
        print(f"Unknown context: {', '.join(unknown)}.\n"
              f"Accepted values: {', '.join(KNOWN_CONTEXTS)}.",
              file=sys.stderr)
        raise SystemExit(2)

    # Check the wiring BEFORE demanding the mandate, and before launching
    # anything: this is a harmless request, not a penetration test. The order
    # matters — discovering a configuration typo must not cost an entry in a
    # client's audit trail.
    if arguments.probe_target:
        if not target_name.startswith(("http://", "https://")):
            print(f"--probe-target aims at an http(s) URL; '{target_name}' is "
                  f"a bundled target, with nothing to configure.",
                  file=sys.stderr)
            raise SystemExit(2)
        try:
            ok = probe_http_target(target_name,
                                   profile=arguments.target_profile)
        except RuntimeError as refusal:
            print(refusal, file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(0 if ok else 1)

    # The mandate BEFORE anything else: we do not send a single request to a
    # third-party system without being able to prove we were entitled to.
    try:
        authorisation = require_mandate(target_name,
                                        arguments.authorisation)
    except MissingAuthorisation as refusal:
        # Advice, not a traceback: the reader must know what to do.
        print(f"Campaign REFUSED.\n{refusal}", file=sys.stderr)
        raise SystemExit(2)

    if authorisation:
        print(f"Mandate: {authorisation['reference']} — "
              f"authorised by {authorisation['authorised_by']}, "
              f"from {authorisation['start']} to {authorisation['end']}.\n")

    folder = arguments.report or "rapports"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # The audit trail is ALWAYS written, even without --rapport: it is the
    # trace of what we sent, not an optional deliverable.
    trail = AuditTrail(Path(folder) / f"{timestamp}-journal.jsonl",
                       target_name, authorisation,
                       context=telemetry(target_name, arguments.target_profile))

    try:
        result = run_campaign(
            choose_target(arguments.target, arguments.target_profile),
            target_name, trail, context,
            adaptive=not arguments.no_adaptation,
            only=scope_patterns(arguments.only),
            excluding=scope_patterns(arguments.excluding))
    except RuntimeError as failure:
        # The target did not answer as expected: unreachable host, HTTP
        # error, non-JSON reply, wrong response path. `cibles/http.py`'s
        # message already says what to fix — it was only drowning in eight
        # lines of Python traceback, while the project insists on giving
        # advice. We add the shortcut that avoids starting again blind.
        print(f"\nCampaign INTERRUPTED: the target did not answer as "
              f"expected.\n{failure}\n\n"
              f"Check the wiring without attacking anything:\n"
              f"  python main.py --target {target_name} --probe-target",
              file=sys.stderr)
        print(f"Audit trail: {trail.path}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        # Even if the campaign raises, the trail must close cleanly.
        seal = trail.close(
            locals().get("result", {}).get("status", "interrupted"),
            call_log())

    result["authorisation"] = authorisation
    # The chain of custody passes from the trail to the REPORT. `build_report`
    # already read these three fields, but nothing filled them: a report came
    # out with no case identifier while the trail had one. The report's reader
    # could not get back to the trace that justifies it — which is exactly
    # what a case identifier is for.
    result["case_id"] = trail.case_id
    result["trail"] = str(trail.path)
    result["trail_seal"] = seal
    result["telemetry"] = telemetry(target_name, arguments.target_profile)
    print(f"\nFinal result: {result['status']}")
    print(f"Audit trail: {trail.path}")

    if arguments.report:
        json_path, md_path = save_report(
            result, target=target_name, folder=arguments.report,
            abridge=arguments.abridge)
        print(f"Report written: {md_path}\n"
              f"Source of truth: {json_path}")

    return result


if __name__ == "__main__":
    cli()
