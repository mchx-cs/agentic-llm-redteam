"""
evaluation/languages.py — Which language each side of an exchange speaks.

A MECHANICAL fact, recorded so that a measurement can be split later without
re-labelling. It is never a label: nothing here touches `expected`, and the
pair is derived from the text every time rather than being decided by hand.

WHY IT EXISTS. The multi-turn harvest is mixed by construction, and nobody had
declared it. `attacker.sequence_turns()` puts a garak complete payload (in
English) on turn 1 and an objective from reconnaissance (in French, because the
demo target is a French library assistant) on turn 2. Measured on the harvest
of 119 entries on 2026-11-15:

    attacker fr -> target fr    77 entries, 22 groups, 10 leaks
    attacker en -> target fr    34 entries                0 leaks
    attacker en -> target en     6 entries                0 leaks
    too short to tell            2 entries

So the English-attacker population holds no positive at all: it is forty
negatives, which is what a corpus needs — the risk a judge runs here is not
missing a leak, it is flagging a visibly offensive conversation where there is
nothing to flag. They are kept, and the pair is recorded so the figure can be
read per population. What it will NEVER yield is a RECALL on crossed
exchanges, for want of a positive there, and that has to be said rather than
implied.

The existing single-turn corpus turned out to mix languages too, without
saying so: 13 of its 90 exchanges are English, and they are `en -> en` — the
deliberate translations (E01-en … E12-en, T02, T05). There is no `en -> fr`
anywhere in it.

HOW IT CLASSIFIES, and its limits. Function words, counted. That is crude on
purpose: a real classifier would be a dependency, and the promise is one. The
limits are therefore explicit:

- a text with no function word at all returns `UNCLEAR`, never a guess. In the
  existing corpus that is exactly right: `E05` is a spelled-out secret, `E06`
  is Base64, `E06-b` is hex. Those strings have no language, and bucketing
  them anyway would be inventing;
- a tie returns `UNCLEAR` as well;
- the word lists were extended ONCE, symmetrically, after a short French
  question ("Combien font 7 fois 8 ?") counted zero words. Adding to one side
  only would tip every tie towards the other language. They are NOT tuned
  further: driving the `?` rate to zero would mean fitting the classifier to
  the very data it is about to split, which is this project's cardinal sin in
  miniature. What matters is that it makes no WRONG call, not that it always
  commits;
- it says nothing about a THIRD language. A German payload would come out
  `UNCLEAR`, which is honest, where guessing would be wrong.

A target can also SWITCH language inside one conversation, and that is real,
not an artefact: 36 of the harvest's conversations have an English attacker
turn then a French one, and the target follows each. `language_pair()`
therefore judges each side as a whole, and `switches_language()` reports the
switch separately for whoever wants it.
"""

import re

FRENCH = "fr"
ENGLISH = "en"
UNCLEAR = "?"

# Function words, which carry no topic and so do not bias towards a subject.
#
# STRICTLY DISJOINT, and a test holds it. A word that exists in both languages
# cannot discriminate, so it must not vote: it adds to both totals and makes a
# tie — hence a `?` — more likely. The first version claimed disjointness and
# was not: `as` was in both (French "tu as", English "as"), and worse, the
# ENGLISH list held `on`, `me` and `a`, all three common French words, which
# would have made English vote on French text. That is the dangerous
# direction, and no sample caught it because French text also matches many
# French words. Found by the test, not by reading.
#
# Dropping `a` costs the commonest English article; `the`, `of`, `and` and
# `to` are far more diagnostic anyway, and none of them is French.
_FRENCH_WORDS = re.compile(
    r"\b(le|la|les|un|une|des|du|de|je|tu|il|elle|nous|vous|ne|pas|que|qui|"
    r"quoi|est|sont|etre|être|avoir|pour|avec|sur|dans|par|mais|donc|"
    r"peux|peut|dois|doit|mes|tes|ses|ton|votre|leur|cette|ces|aux|"
    r"sans|sous|tout|tous|toute|plus|moins|comme|quand|alors|"
    # Interrogatives and everyday verbs: without them a short French question
    # ("Combien font 7 fois 8 ?") counted zero words and came out UNCLEAR.
    r"combien|comment|pourquoi|quel|quelle|quels|quelles|où|oui|non|"
    r"fais|fait|font|dis|dit|dire|donne|veux|veut|sais|sait|vais|va|"
    r"ai|as|suis|es|été|très|bien|aussi|ici|moi|toi|lui|y|en|si|et|ou|à)\b",
    re.IGNORECASE)
_ENGLISH_WORDS = re.compile(
    r"\b(the|of|and|to|a|an|in|that|this|these|those|is|are|was|were|be|been|"
    r"have|has|had|you|your|yours|i|we|they|it|its|not|but|so|for|with|"
    r"by|from|will|would|can|could|must|should|all|any|more|less|when|then|"
    r"at|about|into|"
    # The same addition on the English side. Adding to one list only would
    # bias every tie towards the other language.
    r"how|why|which|what|where|who|yes|no|do|does|did|say|says|tell|give|"
    r"want|wants|know|knows|go|goes|am|very|well|also|here|me|my|if|or)\b",
    re.IGNORECASE)

# Below this many function words in total, a text says nothing about its
# language: "ARCHIVES-7731", "VE9QU0VDUkVUNDI=" or a spelled-out secret are
# neither French nor English, and `?` is the right answer for them.
MINIMUM_WORDS = 1


def language_of(text):
    """
    The dominant language of one text: `fr`, `en`, or `?` when it cannot tell.

    `?` is a real answer, not a failure. A value pasted on its own, a code, a
    tool marker — none of those has a language, and bucketing them anyway
    would be the mechanical guess that this module refuses to make.
    """
    if not text:
        return UNCLEAR
    french = len(_FRENCH_WORDS.findall(text))
    english = len(_ENGLISH_WORDS.findall(text))
    if french + english < MINIMUM_WORDS or french == english:
        return UNCLEAR
    return FRENCH if french > english else ENGLISH


def _sides(entry):
    """
    (everything the attacker said, everything the target said).

    Handles both formats: a conversation carries `turns`, a single-turn
    exchange carries `payload` and `reply`. The format is DERIVED, never
    declared, for the same reason it is derived everywhere else in the
    project — a declared format can disagree with the data.
    """
    turns = entry.get("turns")
    if not turns:
        return entry.get("payload", ""), entry.get("reply", "")
    attacker = " ".join(t["content"] for t in turns
                        if t["role"] == "attacker")
    target = " ".join(t["content"] for t in turns if t["role"] == "target")
    return attacker, target


def language_pair(entry):
    """
    The entry's language pair, as `"en->fr"`.

    Read as "what the attacker writes" -> "what the target answers", because
    that is the asymmetry that matters: the judge's instruction is French, and
    an English attacker turn against a French reply is a population the
    existing corpus does not contain.
    """
    attacker, target = _sides(entry)
    return f"{language_of(attacker)}->{language_of(target)}"


def switches_language(entry):
    """
    True if one side does not speak the same language throughout.

    A separate fact from the pair, and a real one: `sequence_turns` puts an
    English preamble on turn 1 and a French request on turn 2, and the target
    follows each. Folding that into the pair would hide it.
    """
    turns = entry.get("turns")
    if not turns:
        return False
    for role in ("attacker", "target"):
        said = [language_of(t["content"]) for t in turns
                if t["role"] == role]
        if len({s for s in said if s != UNCLEAR}) > 1:
            return True
    return False
