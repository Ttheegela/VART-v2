"""The pattern lists chunk flags and decide rule 4 use (spec 6.4). One module, unit tested, frozen with the
contracts after adversary checkpoint 1: a change here changes labels, so it means re-recording the evals."""

import re

# Spec 6.4's cues: not, never, no longer, pending, planned, not yet, plus the n't forms. Whole words only
# (Plan 1B Task 2): "November", "notice" and "notified" must not count. A bare "no" is left out on purpose:
# "with no exceptions" is a yes.
# Spec 6.4's list is open-ended ("..."), so tbd, to be determined, on the roadmap and in progress count too.
# "scheduled" is deliberately absent; "not only" and "cannot be disabled" (or bypassed, ...) are yeses.
NEGATION = re.compile(
    r"\b(?:not(?! only\b)|never|no longer|not yet|pending|planned|tbd|to be (?:determined|decided|confirmed)"
    r"|on the roadmap|in progress"
    r"|cannot(?! be (?:disabled|bypassed|turned off|switched off|circumvented|overridden))"
    r"|(?:do|does|did|is|are|was|were|has|have|had|ca|wo|should|would|could|must|need)n't)\b",
    re.IGNORECASE,
)
# Unfilled template text: [Company Name] or [frequency] (but not a footnote [1] or a Markdown link: [x](y),
# [x][y] or [[x]]), {{mustache}}, <insert ...> and Lorem ipsum. Redaction tokens such as <PERSON> never match.
# An unchecked task box [ ] is a to-do that is not done yet, so its chunk is not evidence either.
PLACEHOLDER = re.compile(
    r"(?<![\[\]])\[[A-Za-z][A-Za-z .,/'-]{0,38}\](?![(\[])"
    r"|\[ \]"
    r"|\{\{[^{}\n]{1,60}\}\}"
    r"|<\s*(?:insert|enter|add)\b[^<>\n]{0,60}>"
    r"|\blorem ipsum\b",
    re.IGNORECASE,
)
# Instructions aimed at a model. The dev pack plants one obvious injection these patterns catch and one subtle
# one they must not (spec 7.3); the subtle one is left to the stance prompt and decide's rules.
# Each cue needs an attack shape, so policy prose on firewall rules, AI tools or jailbreak detection passes.
# The bare imperative and the system-prompt verbs count only when no negation (not, n't, cannot, never, nor)
# or "who"/"to" comes right before the verb ("Staff who ignore ...", "trained not to ignore ..." are prose).
_NOT_NEGATED = r"(?<!\bnot )(?<!n't )(?<!\bcannot )(?<!\bnever )(?<!\bnor )(?<!\bwho )(?<!\bto )"
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier)\b"
    r"[^.\n]{0,20}\b(?:instructions?|prompts?|rules|directions)\b"
    r"|" + _NOT_NEGATED + r"\b(?:ignore|disregard)\b (?:all |your |these |the )?"
    r"(?:previous |prior |above |earlier |other |system |following )?(?:instructions|prompts)\b"
    r"|\b(?:you are now|from now on,? you are|act as an?|pretend to be)\b[^.\n]{0,30}\b"
    r"(?:ai|assistant|language model|chatbot|llm)\b"
    r"|" + _NOT_NEGATED + r"\b(?:reveal|print|show|repeat|output|display|dump|ignore|disregard)\b"
    r"[^.\n]{0,20}\b(?:system prompt|developer message)\b"
    r"|\bjailbreak (?:mode|prompt)\b"
    r"|\b(?:answer|respond|reply|mark)\b[^.\n]{0,20}\b(?:yes|compliant|verified)\b[^.\n]{0,20}"
    r"\b(?:every|all|each)\b[^.\n]{0,20}\b(?:questions?|items?|controls?)\b",
    re.IGNORECASE,
)
