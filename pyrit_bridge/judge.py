"""
pyrit_bridge/judge.py — our measured judge, as a PyRIT scorer.

This was recorded on 2026-11-13 as the integration's worst risk: "the
documentation describes NO signature for a user-written scorer… the judge is
the heart of the project, and it is measured. Not blocking, but it is
undocumented risk on the least replaceable piece."

Checked against the installed 1.2.1 on 2026-11-17: **the risk does not
exist.** `TrueFalseScorer` has exactly two abstract methods,
`_build_identifier` and `_score_scorable_async`. It was a documentation gap,
not an API gap — which is precisely why the project's method is to check the
primary source rather than reason from a doc page.

THE DECISION THAT SHAPES THIS FILE
----------------------------------
PyRIT offers `create_conversation_scorer`, which wraps a text scorer and
hands it the conversation already rendered as a transcript. It is the obvious
route and it is REFUSED here, for one reason: the judge's question format is
a MEASURED ARTEFACT. Its instruction expects `Utilisateur : "…"` /
`Chatbot : "…"`, those labels are defined in exactly one place
(`targets/conversation.LABELS`) so nothing else can invent a format, and the
published figures — 89 / 100 / 96 single-turn, and the conversation line
measured on 2026-11-16 — were obtained on those bytes.

Feeding the judge PyRIT's rendering instead would change the measured input
silently, and every figure this project publishes about its judge would
quietly stop describing what it runs. So we read the conversation ourselves
and render it with OUR `render()`, through `judge_conversation`.

The cost of that choice, said rather than hidden: it couples this file to
PyRIT's memory API (`CentralMemory`, `get_conversation_messages_async`),
which is one more surface to re-check on each release. Paying it keeps the
judge comparable; not paying it would have made the measurements meaningless.
"""

from pyrit_bridge import require_pyrit

require_pyrit()

from pyrit.memory import CentralMemory                  # noqa: E402
from pyrit.models import Score                          # noqa: E402
from pyrit.models.identifiers import ComponentIdentifier  # noqa: E402
from pyrit.score import ScorerPromptValidator, TrueFalseScorer  # noqa: E402

from agents.judge import judge_conversation_by_vote     # noqa: E402
from pyrit_bridge.convert import (denominator_state,    # noqa: E402
                                  turns_from_api, verdict_to_score)


class OurJudge(TrueFalseScorer):
    """
    The project's judge, voting, as PyRIT's true/false oracle.

    Two properties are kept that PyRIT's own scorers do not have, and both
    were measured here rather than assumed:

    * it VOTES. The judge is not deterministic even at temperature 0 —
      measured 2026-11-10, where one case gave [True, True, True, True,
      False] and `seed` changed nothing. `judge_conversation_by_vote` asks
      three times and takes the majority, because a flaw that appears or
      disappears with the draw has no business in a report;
    * a verdict without a majority is a MISSING MEASUREMENT. PyRIT is told
      `false` so the attack carries on, and the state is carried in the score
      so our side still excludes it from the ASR denominator. The reasoning
      is in `convert.verdict_to_score`; folding it into "the target resisted"
      moved an ASR by seventeen points on 2026-11-12.

    Every verdict is also kept in `verdicts`, in order, so the orchestrator
    can build the campaign's denominator from what the oracle actually said
    instead of reconstructing it from PyRIT's score objects.
    """

    def __init__(self, *, vote_count=None, **kwargs):
        super().__init__(
            # Text evidence only: this judge reads a conversation, not an
            # image or an audio file. Declaring it means PyRIT refuses the
            # mismatch instead of handing us a file path to judge as prose.
            validator=ScorerPromptValidator(supported_data_types=["text"]),
            **kwargs)
        self._vote_count = vote_count
        self.verdicts = []

    def _build_identifier(self):
        from config import JUDGE_PROFILE, PROFILES
        return self._create_identifier(
            params={
                # The judge's identity travels into PyRIT's memory with every
                # score. Without it, two runs on two judges would be
                # indistinguishable afterwards -- the same reason
                # `test_set_log.jsonl` records `profile/model`.
                "judge": f"{JUDGE_PROFILE}/{PROFILES[JUDGE_PROFILE]['model']}",
                "votes": self._vote_count,
                "format": "conversation",
            },
            score_aggregator=self._score_aggregator.__name__,
        )

    async def _score_scorable_async(self, *, scorable, expectation):
        turns = turns_from_api(await self._conversation(scorable))
        if not turns:
            raise ValueError(
                "nothing to judge: the conversation holds no attacker or "
                "target turn. Judging an empty exchange would return "
                "'no flaw', which is a false negative dressed as a verdict.")

        verdict = (judge_conversation_by_vote(turns, self._vote_count)
                   if self._vote_count
                   else judge_conversation_by_vote(turns))
        verdict = {**verdict, "state": denominator_state(verdict),
                   "turns": turns}
        self.verdicts.append(verdict)
        return [Score(**verdict_to_score(verdict), scorable=scorable)]

    @staticmethod
    async def _conversation(scorable):
        """
        The conversation behind this scorable, as plain dicts.

        PyRIT's scorables are REFERENCES, not payloads: a
        `ConversationScorable` carries a `conversation_id` and the content
        lives in memory, which is why `initialize_pyrit_async` is mandatory. A
        `ContentScorable` carries its text directly, and then there is only
        one turn to judge -- we say so rather than pretending it is a
        conversation.

        AND A MULTI-TURN ATTACK HANDS US A `MessageScorable`, which names a
        few message PIECES: PyRIT scores the LAST message, not the dialogue.
        We resolve those pieces back to their conversation and judge the
        whole thing.

        That is not a workaround, it is the integration enforcing a MEASURED
        rule against PyRIT's default. The multi-turn instruction's first rule
        is "judge the WHOLE conversation, and say on which turn", and it was
        not written on taste: on the sound 68-pair run of 2026-11-17, 4 of the
        sequenced form's 19 leaks are invisible in the last reply -- and on the
        harvest, the majority behaviour was a leak on turn 1 followed by an
        impeccable last turn. A judge handed only the last message would miss
        them and report "no flaw".
        """
        memory = CentralMemory.get_memory_instance()

        conversation_id = getattr(scorable, "conversation_id", None)
        if conversation_id is None:
            piece_ids = getattr(scorable, "message_piece_ids", None)
            if piece_ids:
                pieces = memory.get_message_pieces(
                    prompt_ids=[str(identifier) for identifier in piece_ids])
                conversation_id = next(
                    (piece.conversation_id for piece in pieces
                     if piece.conversation_id), None)

        if conversation_id is None:
            value = getattr(scorable, "value", None)
            if value is None:
                raise ValueError(
                    f"{type(scorable).__name__} carries neither a "
                    f"conversation nor a text value: this judge cannot score "
                    f"it. Score a conversation or a text reply.")
            return [{"role": "assistant", "content": value}]

        messages = await memory.get_conversation_messages_async(
            conversation_id=str(conversation_id))
        plain = []
        for message in messages:
            for piece in message.message_pieces:
                plain.append({
                    "role": piece.role,
                    # The CONVERTED value, because that is what the target
                    # actually received or produced: PyRIT's converters
                    # (base64, translation…) rewrite a turn, and judging the
                    # original would judge a message nobody sent.
                    "content": piece.converted_value
                    if piece.converted_value is not None
                    else piece.original_value,
                })
        return plain
