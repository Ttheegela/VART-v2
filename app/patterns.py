"""The pattern lists chunk flags and decide rule 4 use (spec 6.4). One module, unit tested, frozen with the
contracts after adversary checkpoint 1: a change here changes labels, so it means re-recording the evals."""

import re

# Spec 6.4's cues: not, never, no longer, pending, planned, not yet, plus the n't forms. Whole words only
# (Plan 1B Task 2): "November", "notice" and "notified" must not count. A bare "no" is left out on purpose:
# "with no exceptions" is a yes.
NEGATION = re.compile(
    r"\b(?:not|never|no longer|not yet|pending|planned|cannot"
    r"|(?:do|does|did|is|are|was|were|has|have|had|ca|wo|should|would|could|must|need)n't)\b",
    re.IGNORECASE,
)
# Unfilled template text: [Company Name] or [frequency] (but not a footnote [1] or a Markdown link [x](y)),
# {{mustache}}, <insert ...>, and Lorem ipsum. Redaction tokens such as <PERSON> never match.
# An unchecked task box [ ] is a to-do that is not done yet, so its chunk is not evidence either.
PLACEHOLDER = re.compile(
    r"\[[A-Za-z][A-Za-z .,/'-]{0,38}\](?!\()"
    r"|\[ \]"
    r"|\{\{[^{}\n]{1,60}\}\}"
    r"|<\s*(?:insert|enter|add)\b[^<>\n]{0,60}>"
    r"|\blorem ipsum\b",
    re.IGNORECASE,
)
# Instructions aimed at a model. The dev pack plants one obvious injection these patterns catch and one subtle
# one they must not (spec 7.3); the subtle one is left to the stance prompt and decide's rules.
# Each cue needs an attack shape, so policy prose on firewall rules, AI tools or jailbreak detection passes.
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier)\b"
    r"[^.\n]{0,20}\b(?:instructions?|prompts?|rules|directions)\b"
    r"|\b(?:you are now|from now on,? you are|act as an?|pretend to be)\b[^.\n]{0,30}\b"
    r"(?:ai|assistant|language model|chatbot|llm)\b"
    r"|\b(?:reveal|print|show|repeat|ignore|disregard)\b[^.\n]{0,20}\b(?:system prompt|developer message)\b"
    r"|\bjailbreak (?:mode|prompt)\b"
    r"|\b(?:answer|respond|reply|mark)\b[^.\n]{0,20}\b(?:yes|compliant|verified)\b[^.\n]{0,20}"
    r"\b(?:every|all|each)\b[^.\n]{0,20}\b(?:questions?|items?|controls?)\b",
    re.IGNORECASE,
)
