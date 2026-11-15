"""
llm_client.py — THE abstraction layer.

The whole project talks to models ONLY through `ask_llm()` here. No agent
calls Ollama or an API directly. The result: the day you change provider, you
touch config.py and this file — nothing else moves.

This is the guard against hard-coded calls scattered everywhere.

One precision, added in phase 8: the rule aims at the models WE use (judge,
analyst, decoy), so they stay interchangeable from config.py. It does NOT aim
at the attacked target, which is an arbitrary third-party system — often an
application, not a bare model. `targets/http.py` therefore calls it directly,
over urllib, and that is deliberate.
"""

from openai import (APIConnectionError, AuthenticationError, NotFoundError,
                    OpenAI, RateLimitError)
from config import PROFILES, ACTIVE_PROFILE

# The local profiles: those whose server runs on this machine. The advice to
# give differs ("start Ollama" rather than "check your connection").
_LOCAL_HOSTS = ("localhost", "127.0.0.1")

# One client per profile, built on first use then reused. Several profiles can
# serve within one campaign: the target locally, the judge on a remote API,
# for instance.
_clients = {}


class BudgetExceeded(RuntimeError):
    """
    The campaign's call or token cap has been reached.

    An exception DISTINCT from failures (unreachable server, rejected key…):
    reaching your budget is a normal stop, not an error. The orchestrator must
    be able to tell the difference, so it can conclude "campaign cut short"
    instead of "campaign finished" — which do not mean the same thing in a
    report.
    """


# The call log. This module being the ONLY way through to the models, it is
# here that everything is known: how many calls, how many tokens, and above
# all which replies were TRUNCATED. A reply cut off mid-leak reads like a
# normal one: the judge concludes "no vulnerability", and nothing flags the
# error. That is the worst possible defect for a security tool.
#
# It is also here that the budget is applied (phase 11), and where phase 9
# draws its audit trail from.
_CALL_LOG = {"calls": 0, "tokens": 0, "truncated_replies": [],
             "max_calls": None, "max_tokens": None}


def call_log():
    """A copy of the log's state since the last reset."""
    return dict(_CALL_LOG, tronquees=list(_CALL_LOG["truncated_replies"]))


def reset_call_log(max_calls=None, max_tokens=None):
    """
    Starts from a clean counter, and arms the budget of the campaign that
    follows.

    With no cap (the default), nothing is limited: the evaluation scripts
    consume far more than a campaign, and have no reason to be cut off in the
    middle of a measurement. It is therefore the orchestrator that arms the
    budget, deliberately.
    """
    _CALL_LOG.update({"calls": 0, "tokens": 0, "truncated_replies": [],
                      "max_calls": max_calls, "max_tokens": max_tokens})


def _check_budget():
    """
    Raises BudgetExceeded if the cap is reached, BEFORE making the call.

    A call's cost is only known once it has finished: we therefore check what
    has ALREADY been consumed. An accepted consequence: the token cap can be
    overshot by one call at most.
    """
    maximum = _CALL_LOG["max_calls"]
    if maximum is not None and _CALL_LOG["calls"] >= maximum:
        raise BudgetExceeded(
            f"Budget reached: {_CALL_LOG['calls']} call(s), "
            f"cap {maximum}.")

    maximum = _CALL_LOG["max_tokens"]
    if maximum is not None and _CALL_LOG["tokens"] >= maximum:
        raise BudgetExceeded(
            f"Budget reached: {_CALL_LOG['tokens']} tokens, "
            f"cap {maximum}.")


def _client_for(profile):
    if profile not in _clients:
        cfg = PROFILES[profile]
        if not cfg["api_key"]:
            # Fail early, with a clear message, rather than letting the API
            # return an obscure authentication error.
            raise RuntimeError(
                f"Profile '{profile}': API key missing. Set it in the .env "
                f"file at the project root (see config.py)."
            )
        _clients[profile] = OpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            # Without a timeout, a target that never answers would block the
            # campaign for ever.
            timeout=cfg.get("timeout", 60),
            # Automatic retries on a rate limit (error 429): 2 by default in
            # the SDK, more for free tiers.
            max_retries=cfg.get("retries", 2),
        )
    return _clients[profile]


def _validated_history(history):
    """
    The history, checked, or a clear error.

    A malformed history must NOT be ignored silently: the campaign would
    believe it was holding a conversation while sending an isolated turn, and
    the judge would score an exchange stripped of its context. Same family of
    defect as the phase 8 template without `{message}` — a false negative that
    raises nothing.
    """
    if not history:
        return []
    if not isinstance(history, list):
        raise ValueError(
            "`history` must be a list of {'role', 'content'}, "
            f"got: {type(history).__name__}.")

    checked = []
    for position, turn in enumerate(history, start=1):
        if (not isinstance(turn, dict) or "role" not in turn
                or "content" not in turn):
            raise ValueError(
                f"`history`, turn {position}: expected "
                "{'role': ..., 'content': ...}, got " + repr(turn) + ".")
        if turn["role"] not in ("user", "assistant"):
            raise ValueError(
                f"`history`, turn {position}: role "
                f"'{turn['role']}' unknown. Expected 'user' or 'assistant' "
                "— the system instruction goes through `system`, not through "
                "the history.")
        checked.append({"role": turn["role"], "content": str(turn["content"])})
    return checked


def ask_llm(message, system=None, model=None, temperature=None,
            json_format=False, profile=None, max_tokens=None,
            history=None):
    """
    Sends a message to a model and returns its reply (text).

    - message     : the text we send (what the user says).
    - systeme     : optional framing instructions (the model's "role").
    - modele      : to force a specific model; otherwise the profile's.
    - temperature : 0 = near-deterministic replies. Indispensable for a judge:
                    a verdict that changes from one run to the next cannot be
                    measured. None = the provider's default.
    - format_json : forces the model to produce valid JSON. More reliable than
                    guessing YES/NO out of a free-form sentence.
    - profil      : the config.py profile to use; otherwise ACTIVE_PROFILE.
    - max_tokens  : a cap on the reply. Careful: capping risks cutting a leak
                    in half (see _CALL_LOG above).
    - history     : the preceding turns, for a multi-turn conversation
                    (phase 3b). A list of {"role", "content"} inserted BETWEEN
                    the system instruction and the current message, in order.
                    Empty or None = a single turn, the previous behaviour.

    Why the history goes through HERE and not through a direct call: it is
    `llm_client` that counts calls and tokens, hence that applies the budget.
    Multi-turn is precisely the case where cost grows QUADRATICALLY — every
    turn carries forward all that precedes it. A multi-turn attacker calling
    the provider itself would escape the circuit breaker at the exact point
    where it is most useful.

    The parameter names `systeme`, `modele`, `profil` and `format_json` are
    still French: they are passed by keyword from a dozen call sites, and the
    glossary records what renaming a keyword without its call sites costs.
    They move with the operator-facing pass.
    """
    profile = profile or ACTIVE_PROFILE
    model = model or PROFILES[profile]["model"]

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages += _validated_history(history)
    messages.append({"role": "user", "content": message})

    # We only send the options asked for, so the provider keeps its own
    # defaults in the general case.
    options = {}
    if temperature is not None:
        options["temperature"] = temperature
    if json_format:
        # OpenAI's format, understood by Ollama and Groq too.
        options["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        options["max_tokens"] = max_tokens

    # Before anything: the budget. A runaway loop (adaptive agent, a replay
    # inside a replay, a cascade of retries) must hit this wall, not the
    # provider's bill or quota.
    _check_budget()

    try:
        reply = _client_for(profile).chat.completions.create(
            model=model,
            messages=messages,
            **options,
        )
    except (APIConnectionError, NotFoundError, AuthenticationError,
            RateLimitError) as error:
        # The three most common configuration failures. The SDK reports them
        # as "Connection error." or an HTTP code: we translate them into
        # actionable advice, naming the offending profile and model.
        raise RuntimeError(_error_message(profile, model, error)) from error

    _record(reply, profile, model)
    return reply.choices[0].message.content


def _record(reply, profile, model):
    """Logs the call, and remembers replies cut off part way through."""
    _CALL_LOG["calls"] += 1
    usage = getattr(reply, "usage", None)
    if usage and getattr(usage, "total_tokens", None):
        _CALL_LOG["tokens"] += usage.total_tokens

    # "length" = the model hit its output cap, its reply is incomplete. The
    # other stop reasons ("stop", "tool_calls"…) are normal. A provider that
    # reports nothing triggers nothing.
    if getattr(reply.choices[0], "finish_reason", None) == "length":
        _CALL_LOG["truncated_replies"].append({"profile": profile, "model": model})


def _error_message(profile, model, error):
    """Turns an SDK error into clear advice for the user."""
    cfg = PROFILES[profile]
    url = cfg["base_url"]
    header = f"Profile '{profile}' (model '{model}', {url}):"
    local = any(host in url for host in _LOCAL_HOSTS)

    if isinstance(error, APIConnectionError):
        if local:
            return (f"{header} the server is not answering.\n"
                    f"  Is Ollama running? Check with: ollama list\n"
                    f"  If it is down, start it: ollama serve")
        return (f"{header} cannot reach the server.\n"
                f"  Check your connection and the 'base_url' in config.py.")

    if isinstance(error, RateLimitError):
        # The SDK retries by itself on per-minute limits (see "relances" in
        # config.py). If it gives up, the DAILY quota is reached: retrying
        # will change nothing, you have to wait or switch.
        return (f"{header} the provider's quota is reached.\n"
                f"  Wait for the window it states, or put the judge back on "
                f"local\n"
                f"  (JUDGE_PROFILE=local in .env).\n"
                f"  Provider detail: {error}")

    if isinstance(error, NotFoundError):
        if local:
            return (f"{header} that model is not installed.\n"
                    f"  Download it with: ollama pull {model}")
        return (f"{header} the provider does not know that model.\n"
                f"  Check its exact name (the profile's environment "
                f"variable).")

    return (f"{header} API key refused.\n"
            f"  Check the key in the .env file at the project root.")
