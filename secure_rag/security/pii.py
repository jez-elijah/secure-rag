"""PII detection and reversible redaction using Microsoft Presidio.

One Redactor per request: the same value always maps to the same placeholder
(<PERSON_1>, <EMAIL_ADDRESS_1>, ...) across the question and every chunk, so the
model can still reason about "the same person" without ever seeing the real value.
"""
import re

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN",
    "EMPLOYEE_ID", "DATE_OF_BIRTH", "US_STREET_ADDRESS",
]
# High-sensitivity identifiers stay hidden even in the final answer shown to the user.
NEVER_RESTORE = {"US_SSN", "DATE_OF_BIRTH", "US_STREET_ADDRESS"}
SCORE_THRESHOLD = 0.35

_MONTH = "(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_DATE = rf"(?:{_MONTH} +\d{{1,2}}, +\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}})"
_STREET_SUFFIX = (
    "Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Court|Ct|Way|Place|Pl"
)

# (entity, regex, score). Case-sensitive on purpose, so ordinary lowercase text can't match.
CUSTOM_RECOGNIZERS = [
    ("EMPLOYEE_ID", r"\bEMP-\d{5}\b", 0.9),
    # Only a date directly after "date of birth" / "DOB" / "born", so ordinary dates survive.
    ("DATE_OF_BIRTH", rf"\b(?i:date of birth|dob|born(?: on)?)[:,]? +{_DATE}", 0.85),
    # Street address, plus optional ", City, ST 12345" so the whole address is one span.
    (
        "US_STREET_ADDRESS",
        rf"\b\d{{1,6}} +(?:[A-Z][A-Za-z0-9.'-]* +){{1,3}}(?:{_STREET_SUFFIX})\b\.?"
        r"(?:, +[A-Z][A-Za-z.]*(?: +[A-Z][A-Za-z.]*)*, +[A-Z]{2} +\d{5}(?:-\d{4})?)?",
        0.85,
    ),
]

_analyzer = None


def _get_analyzer():
    """Load Presidio lazily (the spaCy model takes a few seconds) and add custom recognizers."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
        for entity, regex, score in CUSTOM_RECOGNIZERS:
            _analyzer.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity=entity,
                    patterns=[Pattern(entity.lower(), regex, score)],
                    global_regex_flags=re.MULTILINE,
                )
            )
    return _analyzer


class Redactor:
    def __init__(self):
        self.forward = {}  # (entity, value) -> placeholder
        self.reverse = {}  # placeholder -> (entity, value)
        self.counts = {}   # entity -> how many distinct values were seen

    def _placeholder(self, entity, value):
        key = (entity, value.strip().lower())
        if key not in self.forward:
            n = self.counts[entity] = self.counts.get(entity, 0) + 1
            placeholder = f"<{entity}_{n}>"
            self.forward[key] = placeholder
            self.reverse[placeholder] = (entity, value)
        return self.forward[key]

    def redact(self, text):
        results = _get_analyzer().analyze(
            text=text, language="en", entities=ENTITIES, score_threshold=SCORE_THRESHOLD
        )
        # Keep the earliest / longest match when detections overlap.
        chosen, last_end = [], -1
        for r in sorted(results, key=lambda r: (r.start, -(r.end - r.start))):
            if r.start >= last_end:
                chosen.append(r)
                last_end = r.end
        # Replace from the end so earlier offsets stay valid.
        for r in reversed(chosen):
            value = text[r.start:r.end]
            end = r.end
            if r.entity_type == "PERSON":
                # spaCy sometimes swallows a possessive ("Priya Raman's"). Keep it outside the
                # placeholder so the same person always maps to the same placeholder.
                value = re.sub(r"['\u2019]s$", "", value)
                end = r.start + len(value)
            text = text[:r.start] + self._placeholder(r.entity_type, value) + text[end:]
        return text

    def restore(self, text):
        """Put real values back into the model's answer, except entity types in NEVER_RESTORE."""
        for placeholder, (entity, value) in self.reverse.items():
            text = text.replace(placeholder, "[REDACTED]" if entity in NEVER_RESTORE else value)
        return text
