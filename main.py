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

    print("=== Campagne ===\n")
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
        return _finish({"statut": "budget_epuise", "fiche": None,
                        "plan": {"essais": [], "candidats": [],
                                 "ecartees": []},
                        "constats": [], "ecourtee": str(stop)})
    # The context comes from the OPERATOR, not from a probe: a target does not
    # know what its output is rendered in, and asking it would invite
    # hallucination. So we add it afterwards, without touching the observed
    # facts.
    profile["contexte"] = list(context)
    print(summarise_profile(profile))

    # --- 2. Planning: what to launch, and in what order? -------------------
    print("\n--- Plan ---")
    plan = plan_campaign(profile, MAX_ESSAIS, only, excluding)
    print(summarise_plan(plan))

    if not plan["essais"]:
        print("\n>>> Aucun essai applicable à cette cible. Campagne terminée.")
        return _finish({"statut": "aucun_essai", "fiche": profile,
                        "plan": plan, "constats": []})

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
        payload = next_attempt(plan["candidats"],
                               observations if adaptive else (), launched)
        if payload is None:
            print(">>> Vivier épuisé : plus aucun essai applicable.")
            break
        launched.append(payload)

        print(f"--- Essai {number}/{MAX_ESSAIS} ---")
        print(f"  [Attaquant] {payload['technique']} / "
              f"{payload['objectif'] or 'payload complet'} "
              f"/ {payload['transformation']}")
        if payload.get("raisons_adaptation"):
            # The net first: an attempt can carry both a bonus and a penalty,
            # and without it the reasons look contradictory.
            print(f"  [Adaptation] solde {payload['score_adaptation']:+d} "
                  f"sur sa priorité de départ "
                  f"({payload['priorite']}) :")
            for reason in payload["raisons_adaptation"]:
                print(f"               - {reason}")
        print(f"              envoie : {payload['texte']}")

        try:
            # A reply cut off by the target's output cap reads like a complete
            # one: the verdict would then be worth nothing.
            truncated_before = len(call_log()["tronquees"])
            reply = ask_target(payload["texte"])
            truncated = len(call_log()["tronquees"]) > truncated_before
            if trail:
                trail.record_exchange("attaque", payload["texte"], reply,
                                      truncated)
            print(f"  [Cible]     répond : {reply}")
            if truncated:
                print("  /!\\        réponse TRONQUÉE : une fuite a pu être "
                      "coupée en deux, le verdict ci-dessous n'est pas fiable.")

            # Voting: the judge is not deterministic on borderline cases, and
            # a vulnerability that appears with the draw has no business in a
            # report.
            verdict = judge_by_vote(payload["texte"], reply)
            if trail:
                trail.record_verdict(number, verdict)
            print(f"  [Arbitre]   enfreint={verdict['reussi']} "
                  f"({verdict['critere']}, votes {verdict['votes']}) : "
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
                states.append("reponse_tronquee")
                continue
            if verdict["reussi"] is None:
                states.append("juge_indecis")
                continue
            if verdict["reussi"] is False:
                states.append("resiste")
                continue

            # --- 4. Replay check, if a value was disclosed -----------------
            replay_check = None
            if verdict["critere"] == "divulgation":
                # The replay gets `judge` without voting: it already queries
                # the target several times, which smooths the noise. Voting on
                # top would cost nine calls where three are enough.
                replay_check = verify_by_replay(
                    payload["texte"], verdict["valeur"],
                    trail.trace("rejeu", ask_target) if trail
                    else ask_target,
                    judge,
                )
                print(f"  [Rejeu]     {replay_check['statut']} : "
                      f"{replay_check['explication']}")

                if replay_check["statut"] == "hallucination_probable":
                    # The target made it up: nothing leaked, no finding.
                    # Scorable all the same — the attack did fail, and the
                    # replay established it instead of assuming it.
                    states.append("hallucination")
                    print("  >>> Valeur inventée par la cible : on continue.\n")
                    continue
        except BudgetExceeded as stop:
            # A NORMAL stop, not a failure: we keep what has been found so
            # far, and we will say plainly that the plan did not run to its
            # end. The attempt in flight is lost, and that is accepted.
            cut_short = str(stop)
            print(f"\n>>> {stop}")
            print(f">>> Campagne ÉCOURTÉE à l'essai {number} sur "
                  f"{MAX_ESSAIS}.")
            break

        print("  >>> Constat retenu.\n")
        states.append("faille")
        findings.append({
            "essai": number,
            "payload": payload,
            "reponse": reply,
            "verdict": verdict,
            # None (compliance, no value), or the replay's result:
            # "confirmee", "contradictoire", "inconcluant"…
            "verification": replay_check,
            "tronquee": truncated,
        })

    if not cut_short:
        print(f">>> Budget d'essais épuisé : {len(findings)} constat(s).")

    return _finish({
        # A plan cut short must NEVER present itself as a finished plan:
        # "no finding" does not mean the same thing in the two cases.
        "statut": ("budget_epuise" if cut_short
                   else "constats" if findings else "aucun_constat"),
        "fiche": profile,
        "plan": plan,
        "constats": findings,
        # The attempts REALLY sent, and what we learned along the way. It is
        # from these that the report draws its coverage: since adaptation, the
        # initial plan is no longer what was launched, and announcing the
        # plan's coverage would be a lie by omission.
        "lances": launched,
        "observations": observations,
        # Each attempt's outcome, so the report computes an ASR over a DEFINED
        # denominator rather than over the number of sends.
        "etats": states,
        # The scope asked for: the report MUST say it, otherwise a campaign
        # restricted to one family would present its coverage as complete.
        "perimetre": {"seulement": list(only), "sauf": list(excluding)},
        # Are the attempts i.i.d.? Two conditions, both necessary: no
        # adaptation (otherwise the next one depends on the previous replies)
        # and a single technique launched (otherwise payloads from different
        # families do not share the same probability of success). When both
        # hold — typically `--seulement X --sans-adaptation` — the report can
        # finally bound its "no finding", which is precisely what pass@k asks.
        "essais_independants": (
            not adaptive
            and len({a["technique"] for a in launched}) <= 1
            and len(launched) > 0),
        "ecourtee": cut_short,
    })


def _finish(result):
    """Attaches the call log and warns if any reply was cut off."""
    result.setdefault("ecourtee", None)
    result.setdefault("lances", [])
    result.setdefault("etats", [])
    result.setdefault("perimetre", {"seulement": [], "sauf": []})
    result.setdefault("essais_independants", False)
    result.setdefault("observations", [])
    result.setdefault("payloads", _payload_provenance())
    result["journal"] = call_log()
    truncated_count = len(result["journal"]["tronquees"])

    print(f"\n{result['journal']['appels']} appel(s) au LLM, "
          f"{result['journal']['tokens']} tokens.")
    if truncated_count:
        # A "no vulnerability" obtained on cut-off replies is worth nothing:
        # say so plainly rather than letting it look like coverage.
        print(f"/!\\ {truncated_count} réponse(s) tronquée(s) : les verdicts "
              f"correspondants sont peu fiables, et un « aucune faille » "
              f"pourrait masquer une fuite coupée en deux.")
    return result


def _payload_provenance():
    """Which library the campaign worked with, and how old it is."""
    from agents.attaquant import SNAPSHOT_AGE_SUSPECT, load_library

    garak = load_library().get("_garak")
    if not garak:
        return None
    age = garak.get("age_jours")
    return {**garak,
            "perime": age is not None and age > SNAPSHOT_AGE_SUSPECT}


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
    parser = argparse.ArgumentParser(description="Lance une campagne de test.")
    parser.add_argument(
        "--cible", default=None,
        help="'leurre' (défaut), 'mock', ou une URL http(s). "
             "Sinon la valeur de CIBLE dans .env.")
    parser.add_argument(
        "--rapport", nargs="?", const="rapports", default=None,
        metavar="DOSSIER",
        help="écrire resultat.json et rapport.md dans DOSSIER "
             "(par défaut : rapports/).")
    parser.add_argument(
        "--abreger", action="store_true",
        help="tronquer payloads et réponses dans rapport.md (pour partager "
             "un rapport sans réponses verbatim, ou publier un exemple). "
             "resultat.json garde tout.")
    parser.add_argument(
        "--seulement", default="", metavar="MOTIFS",
        help="restreindre la campagne, par famille OWASP (LLM07), module "
             "garak (dan) ou technique (fuite-prompt-systeme) ; plusieurs "
             "motifs séparés par des virgules. Le rapport dit toujours que "
             "la campagne était restreinte.")
    parser.add_argument(
        "--sauf", default="", metavar="MOTIFS",
        help="écarter des techniques, mêmes motifs que --seulement. Sert à "
             "respecter une portée de mandat qui exclut des techniques ; "
             "l'emporte sur --seulement.")
    parser.add_argument(
        "--sans-adaptation", action="store_true", dest="sans_adaptation",
        help="suivre le plan statique sans rien apprendre des réponses. "
             "Sert de témoin pour mesurer ce que l'adaptation apporte ; "
             "inutile en usage normal.")
    parser.add_argument(
        "--profil-cible", default=None, metavar="NOM", dest="profil_cible",
        help="forme d'API de la cible, au lieu de décrire CIBLE_CORPS et "
             "CIBLE_CHEMIN_REPONSE à la main : "
             + ", ".join(TARGET_PROFILES)
             + ". L'emporte sur CIBLE_CORPS et CIBLE_CHEMIN_REPONSE de .env : "
               "la ligne de commande est plus spécifique. Pour un corps sur mesure, "
               "règle .env et ne passe pas de profil.")
    parser.add_argument(
        "--tester-cible", action="store_true", dest="tester_cible",
        help="envoyer UN message anodin pour vérifier le branchement, puis "
             "s'arrêter. Aucune attaque, aucun mandat requis : à lancer "
             "avant toute campagne contre une cible réelle.")
    parser.add_argument(
        "--contexte", default="", metavar="LISTE",
        help="ce que l'application AUTOUR de la cible fait de sa sortie, "
             "séparé par des virgules : "
             + ", ".join(KNOWN_CONTEXTS)
             + ". Certaines familles de sondes n'ont aucun sens sans ça, et "
               "une cible ne peut pas le déclarer elle-même.")
    parser.add_argument(
        "--autorisation", default=AUTHORISATION_FILE, metavar="FICHIER",
        help=f"mandat couvrant la cible (défaut : {AUTHORISATION_FILE}). "
             f"Inutile pour une cible locale.")
    arguments = parser.parse_args(arguments)

    target_name = arguments.cible or TARGET

    # The target's NAME first, and this is a correction: a typo ("demo:9",
    # "leure") used to come out either as a Python traceback or — worse — as
    # an authorisation message, which talked about a mandate to someone who
    # had simply mistyped a letter. So we check the name before anything,
    # which sends no request and does not disturb the mandate's order.
    try:
        choose_target(target_name, arguments.profil_cible)
    except (ValueError, RuntimeError) as refusal:
        print(f"Cible inutilisable.\n{refusal}", file=sys.stderr)
        raise SystemExit(2)

    # An unknown context name is a TYPO, not an absent context: accepting it
    # silently would skip whole families without anyone understanding why.
    # Same logic as an unknown profile, which fails at import with the list of
    # valid values.
    context = [c.strip() for c in arguments.contexte.split(",") if c.strip()]
    unknown = [c for c in context if c not in KNOWN_CONTEXTS]
    if unknown:
        print(f"Contexte inconnu : {', '.join(unknown)}.\n"
              f"Valeurs acceptées : {', '.join(KNOWN_CONTEXTS)}.",
              file=sys.stderr)
        raise SystemExit(2)

    # Check the wiring BEFORE demanding the mandate, and before launching
    # anything: this is a harmless request, not a penetration test. The order
    # matters — discovering a configuration typo must not cost an entry in a
    # client's audit trail.
    if arguments.tester_cible:
        if not target_name.startswith(("http://", "https://")):
            print(f"--tester-cible vise une URL http(s) ; '{target_name}' est "
                  f"une cible livrée, qui n'a rien à configurer.",
                  file=sys.stderr)
            raise SystemExit(2)
        try:
            ok = probe_http_target(target_name, profile=arguments.profil_cible)
        except RuntimeError as refusal:
            print(refusal, file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(0 if ok else 1)

    # The mandate BEFORE anything else: we do not send a single request to a
    # third-party system without being able to prove we were entitled to.
    try:
        authorisation = require_mandate(target_name, arguments.autorisation)
    except MissingAuthorisation as refusal:
        # Advice, not a traceback: the reader must know what to do.
        print(f"Campagne REFUSÉE.\n{refusal}", file=sys.stderr)
        raise SystemExit(2)

    if authorisation:
        print(f"Mandat : {authorisation['reference']} — "
              f"autorisé par {authorisation['autorise_par']}, "
              f"du {authorisation['debut']} au {authorisation['fin']}.\n")

    folder = arguments.rapport or "rapports"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # The audit trail is ALWAYS written, even without --rapport: it is the
    # trace of what we sent, not an optional deliverable.
    trail = AuditTrail(Path(folder) / f"{timestamp}-journal.jsonl",
                       target_name, authorisation,
                       context=telemetry(target_name, arguments.profil_cible))

    try:
        result = run_campaign(
            choose_target(arguments.cible, arguments.profil_cible),
            target_name, trail, context,
            adaptive=not arguments.sans_adaptation,
            only=scope_patterns(arguments.seulement),
            excluding=scope_patterns(arguments.sauf))
    except RuntimeError as failure:
        # The target did not answer as expected: unreachable host, HTTP
        # error, non-JSON reply, wrong response path. `cibles/http.py`'s
        # message already says what to fix — it was only drowning in eight
        # lines of Python traceback, while the project insists on giving
        # advice. We add the shortcut that avoids starting again blind.
        print(f"\nCampagne INTERROMPUE : la cible n'a pas répondu comme "
              f"attendu.\n{failure}\n\n"
              f"Vérifie le branchement sans rien attaquer :\n"
              f"  python main.py --cible {target_name} --tester-cible",
              file=sys.stderr)
        print(f"Piste d'audit : {trail.path}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        # Even if the campaign raises, the trail must close cleanly.
        seal = trail.close(
            locals().get("result", {}).get("statut", "interrompue"),
            call_log())

    result["autorisation"] = authorisation
    # The chain of custody passes from the trail to the REPORT. `build_report`
    # already read these three fields, but nothing filled them: a report came
    # out with no case identifier while the trail had one. The report's reader
    # could not get back to the trace that justifies it — which is exactly
    # what a case identifier is for.
    result["case_id"] = trail.case_id
    result["piste"] = str(trail.path)
    result["sceau_piste"] = seal
    result["telemetrie"] = telemetry(target_name, arguments.profil_cible)
    print(f"\nRésultat final : {result['statut']}")
    print(f"Piste d'audit : {trail.path}")

    if arguments.rapport:
        json_path, md_path = save_report(
            result, target=target_name, folder=arguments.rapport,
            abridge=arguments.abreger)
        print(f"Rapport écrit : {md_path}\n"
              f"Source de vérité : {json_path}")

    return result


if __name__ == "__main__":
    cli()
