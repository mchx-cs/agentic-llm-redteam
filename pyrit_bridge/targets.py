"""
pyrit_bridge/targets.py — the two PyRIT targets this project supplies.

PyRIT needs two distinct things it calls by the same name, and confusing them
is how the budget guard gets lost:

  * the ATTACKER model, which writes the next turn. It is OURS, so it must go
    through `ask_llm()` — that is `OurModel` below, and it is what keeps
    `CALL_BUDGET`, `TOKEN_BUDGET` and the truncated-reply log alive;
  * the SYSTEM UNDER TEST, an arbitrary third party. It is reached through
    phase 8's contract, `ask(message, history=...) -> str`, and deliberately
    NOT through `ask_llm()` — the rule clarified in phase 8 covers the models
    we use, never the target under attack.

Both are thin: every decision they make is in `convert.py`, which imports no
PyRIT and is therefore tested in continuous integration, where PyRIT cannot
even be installed.
"""

from pyrit_bridge import require_pyrit

require_pyrit()

from pyrit.models import Message                        # noqa: E402
from pyrit.models.target.target_capabilities import (   # noqa: E402
    TargetCapabilities)
from pyrit.prompt_target import PromptTarget, TargetConfiguration  # noqa: E402

from pyrit_bridge.convert import (api_from_turns,  # noqa: E402
                                  system_from_api, turns_from_api)
from targets.conversation import MAX_TURNS, require_conversation  # noqa: E402


def _capabilities(*, system_prompt):
    """
    What a target of ours declares to PyRIT.

    `supports_editable_history` is TRUE for both: our contract takes the whole
    history on every call and holds no state of its own, so PyRIT may rewrite
    it between turns — which is exactly what Crescendo's backtracking does.

    `supports_system_prompt` is the ASYMMETRY, and it is not cosmetic. I first
    declared one shared configuration for both targets, with `False`
    everywhere, reasoning that a system prompt belongs to the system under
    test. That reasoning is right for the target and wrong for the attacker:

      * the ATTACKER MODEL is ours, and a system prompt is how PyRIT tells it
        how to attack. `RedTeamingAttack` enforces it, which is how the error
        was found: "Target must natively support 'supports_system_prompt';
        adaptation is not acceptable for this consumer." `ask_llm` has a
        `system=` parameter, so honouring it costs nothing;
      * the TARGET UNDER TEST must NOT accept one. Its system prompt is what
        we are trying to extract; letting PyRIT set one would mean attacking a
        system we configured instead of the one the client deployed, and the
        finding would be about our own prompt.

    Declaring one capability set for both hid that distinction — the same
    distinction this file's own docstring opens with. It was caught by RUNNING
    the attack, not by reading the code.
    """
    return TargetConfiguration(capabilities=TargetCapabilities(
        supports_multi_turn=True,
        supports_editable_history=True,
        supports_system_prompt=system_prompt,
    ))


def _pieces(conversation):
    """A PyRIT conversation reduced to the plain dicts `convert` works on."""
    plain = []
    for message in conversation:
        for piece in message.message_pieces:
            plain.append({"role": piece.role,
                          "content": piece.converted_value
                          if piece.converted_value is not None
                          else piece.original_value})
    return plain


def _reply(text):
    """A PyRIT reply carrying our target's text."""
    return [Message.from_prompt(prompt=text, role="assistant")]


class OurModel(PromptTarget):
    """
    PyRIT's attacker model, routed through `ask_llm()`.

    This class is the whole reason the bridge exists. Without it PyRIT builds
    its own `OpenAIChatTarget`, reaches a provider directly, and the project's
    only call counter never sees it — so the circuit breaker is disarmed in
    the one configuration where cost grows quadratically.

    `BudgetExceeded` is deliberately NOT caught. It is a normal stop, not a
    failure, and it has to reach the orchestrator so the campaign can conclude
    "cut short" rather than "crashed". Swallowing it here would turn a clean
    stop into a truncated attack reported as complete.
    """

    # Measured on the first real run, 2026-11-17: with the profile's default
    # ceiling, llama3.2 cut its own JSON mid-string — `"last_response_summary":
    # "` — and PyRIT retried SEVEN times, so a third of the 21 calls bought
    # nothing. PyRIT's attacks ask their attacker model for structured JSON
    # (next_message, rationale, last_response_summary), which is longer than a
    # chat turn, and a cut-off object is simply invalid.
    #
    # Not silent, at least: invalid JSON raises there instead of passing for
    # an answer, which is the opposite of the defect `call_log` was built for.
    # But it is budget spent, so the ceiling is raised here by default and the
    # truncations stay visible in `call_log()["truncated_replies"]`.
    DEFAULT_MAX_TOKENS = 1024

    def __init__(self, *, profile=None, temperature=None,
                 max_tokens=DEFAULT_MAX_TOKENS, **kwargs):
        super().__init__(custom_configuration=_capabilities(
                             system_prompt=True),
                         model_name=profile or "active profile", **kwargs)
        self._profile = profile
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def _send_prompt_to_target_async(self, *, normalized_conversation):
        from llm_client import ask_llm

        turns = turns_from_api(_pieces(normalized_conversation))
        if not turns:
            raise ValueError(
                "PyRIT asked the attacker model for a turn with no usable "
                "message. A system-only or tool-only conversation is not a "
                "prompt; see convert.turns_from_api, which drops roles the "
                "judge must never read as a chatbot turn.")

        # The last attacker turn is the question; everything before it is the
        # history. `ask_llm` takes them separately, which is also what makes
        # the single-turn and multi-turn paths one code path.
        current, before = turns[-1], turns[:-1]
        reply = ask_llm(current["content"],
                        system=system_from_api(_pieces(
                            normalized_conversation)),
                        history=api_from_turns(before),
                        profile=self._profile,
                        temperature=self._temperature,
                        max_tokens=self._max_tokens)
        return _reply(reply)


class OurTarget(PromptTarget):
    """
    The system under test, reached through phase 8's contract.

    Wrapping `ask` rather than reimplementing it is what lets PyRIT attack
    everything the project already supports — `demo`, `decoy`, `mock`, an HTTP
    endpoint — with no new adapter, and it keeps the audit trail working: a
    traced `ask` stays a `message -> str` function, so `trail.trace()` wraps
    this target exactly as it wraps a single-turn one.

    The conversation capability is CHECKED, not assumed. A target that does
    not declare it refuses here, loudly, instead of silently seeing isolated
    messages while PyRIT believes it is holding a dialogue — the defect the
    conversation contract was written to prevent.
    """

    # Keyword-only, and not by taste: PyRIT ENFORCES it at class creation
    # (`enforce_keyword_only_init`), so a positional `ask` raises a TypeError
    # before an instance exists. A contract checked that early is a good one;
    # it is also one more thing to re-check on each release.
    def __init__(self, *, ask, name="this target", **kwargs):
        require_conversation(ask, name)
        super().__init__(custom_configuration=_capabilities(
                             system_prompt=False),
                         model_name=name, **kwargs)
        self._ask = ask
        self._name = name

    async def _send_prompt_to_target_async(self, *, normalized_conversation):
        turns = turns_from_api(_pieces(normalized_conversation))
        if not turns:
            raise ValueError(
                f"PyRIT sent {self._name} a conversation with no usable "
                f"message.")
        if len(turns) > 2 * MAX_TURNS:
            # Every loop in this project is bounded, and this one carries the
            # whole history forward on each turn. PyRIT has its own turn
            # budget; this is the floor under it, so a misconfigured attack
            # cannot cost without limit.
            raise ValueError(
                f"{len(turns) // 2} turns against {self._name}, maximum "
                f"{MAX_TURNS}. Each turn carries everything before it: the "
                f"bound is there so the cost cannot climb unwatched. Lower "
                f"the attack's max_turns.")

        current, before = turns[-1], turns[:-1]
        return _reply(self._ask(current["content"],
                                history=api_from_turns(before)))
