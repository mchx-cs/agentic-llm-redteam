"""
targets/indirect.py — The target contract extended to a payload that arrives
through CONTENT THE TARGET READS, rather than from the user.

Until now every payload reached the target as the current user message. The
contract does not change:

    ask(message, history=None) -> str

This module adds, ALONGSIDE it, a second way in — the one a real engagement
uses against a retrieval-augmented application:

    ask.plant(text) -> str      # put `text` where the target will read it
    ask.indirect = True         # and DECLARE that you can

A target able to do that declares it. One that cannot makes an indirect
attempt be REFUSED.

Why the channel is DECLARED rather than guessed
-----------------------------------------------
Exactly the reasoning of `targets/conversation.py`, and for a defect this
project has now paid for three times.

A target handed a planted note it silently discards would leave the campaign
believing it ran an indirect attack while the model never saw the note. The
judge would score an innocuous exchange, the report would say the family was
tested, and "indirect injection adds nothing" would be a false conclusion with
nothing to flag it. That is the family of the template without `{message}`
(phase 8), of the conversation capability guessed rather than declared (phase
3b) and of the three chain-of-custody fields nobody filled (phase 14): a
defect that raises nothing, breaks no test, and INVERTS the conclusion.

So silence means refusal, never permission — the same choice as `--context`,
where an undeclared context skips the family instead of launching it blind.

Why the note is NOT planted in the conversation history
-------------------------------------------------------
This is the trap, and it is worth naming because the history is right there
and would look like the cheap way to do it.

A payload put in an earlier ATTACKER turn is in the conversation. The judge
reads the conversation, so it would SEE the instruction — and what it scored
would be an ordinary multi-turn attack, which `measure_modes` has already
measured. The whole point of indirect delivery is that the instruction reaches
the model from somewhere the judge cannot see: that is why the visible-outcome
half is scorable at all (measured 2026-11-25, `divulgation` 10/10 on a reply
volunteering a code after an innocuous question), and why the obedience-only
half is not.

A note must therefore come from somewhere a THIRD PARTY wrote: a suggestion
box, a comment, a shared page, an uploaded file. Not from a turn of ours.

What this does NOT give us
--------------------------
The judge will score the OUTCOME correctly and can never say the injection was
indirect — the document is not in the exchange. That provenance is ours to
record, on the attempt, and it is not this module's job.
"""

#: The longest note a target is asked to hold. A planted note becomes part of
#: the system prompt, so an unbounded note is an unbounded prompt — and some
#: garak payloads run past 2,500 characters.
#:
#: Above it, a target REFUSES rather than truncating. The reason is the one
#: measured on the GET transport: a truncated payload reaches the target in
#: half, the reply is harmless, the judge says "no finding" and the report
#: concludes the target is safe. A cut note carries no sign of its own
#: truncation, so it is a silent false negative — the error this project
#: exists to make loud.
NOTE_LIMIT = 4000


def supports_indirect(ask):
    """
    Can a payload be planted where this target will read it?

    NO by default. A target that does not declare the channel is treated as
    reachable only through the user message.
    """
    return bool(getattr(ask, "indirect", False)) and callable(
        getattr(ask, "plant", None))


def require_indirect(ask, target_name="this target"):
    """Raise with an instruction if the target has no indirect channel."""
    if supports_indirect(ask):
        return
    raise RuntimeError(
        f"{target_name} has no content a payload can be planted in: an "
        f"indirect injection is not testable against it.\n"
        f"`docs` is the bundled target that has one. An HTTP endpoint does "
        f"not yet: reaching a real application's write surface — an upload, a "
        f"comment, a shared page — is a second endpoint to configure, not a "
        f"variant of this one.\n"
        f"Run an ordinary campaign, or aim at `--target docs`.")


def check_note(text):
    """
    Raise if `text` cannot be planted as it stands.

    Called by the target at PLANT time, not at reply time: you do not
    discover that a client's throughput was spent on a note the target
    silently dropped.
    """
    if text is None:
        return None
    text = str(text)
    if not text.strip():
        raise ValueError(
            "an empty note plants nothing: the target would answer from its "
            "genuine documents, and the attempt would look like a refusal.")
    if len(text) > NOTE_LIMIT:
        raise ValueError(
            f"note of {len(text)} characters, limit {NOTE_LIMIT}. It is "
            f"REFUSED rather than truncated: half a payload produces a "
            f"harmless reply, and a report that reads as 'the target "
            f"resisted'. Raise `targets.indirect.NOTE_LIMIT` knowingly, or "
            f"record the attempt as not sent.")
    return text
