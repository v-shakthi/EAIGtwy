"""
middleware/pii_redactor.py
==========================
PII detection and redaction using Microsoft Presidio.
Scrubs sensitive entities from prompts BEFORE they leave the enterprise network.

In production: swap the in-process Presidio engine for a dedicated Presidio server
behind your private network perimeter.
"""

import re
from dataclasses import dataclass
from config import settings

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False


@dataclass
class RedactionResult:
    redacted_text: str
    entities_found: list[str]
    redaction_count: int


class PIIRedactor:
    """
    Wraps Presidio Analyzer + Anonymizer for enterprise PII scrubbing.
    Falls back to regex-based redaction if Presidio is not installed.
    """

    def __init__(self):
        self.enabled = settings.pii_redaction_enabled
        self.entities = settings.pii_entities

        if PRESIDIO_AVAILABLE:
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._backend = "presidio"
        else:
            # Lightweight regex fallback — covers the most common cases
            self._backend = "regex"
            self._patterns = {
                "EMAIL_ADDRESS": re.compile(
                    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b'
                ),
                "PHONE_NUMBER": re.compile(
                    r'\b(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?)(\d{3}[\s.\-]?\d{4})\b'
                ),
                "CREDIT_CARD": re.compile(
                    r'\b(?:\d{4}[\s\-]?){3}\d{4}\b'
                ),
                "US_SSN": re.compile(
                    r'\b\d{3}-\d{2}-\d{4}\b'
                ),
                "IP_ADDRESS": re.compile(
                    r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
                ),
            }

    def redact(self, text: str) -> RedactionResult:
        """
        Detects and redacts PII from text. Returns redacted text and a summary.
        Original text is NEVER stored or logged.
        """
        if not self.enabled:
            return RedactionResult(
                redacted_text=text,
                entities_found=[],
                redaction_count=0,
            )

        if self._backend == "presidio":
            return self._redact_presidio(text)
        else:
            return self._redact_regex(text)

    def _redact_presidio(self, text: str) -> RedactionResult:
        results = self._analyzer.analyze(
            text=text,
            entities=self.entities,
            language="en",
        )

        if not results:
            return RedactionResult(
                redacted_text=text,
                entities_found=[],
                redaction_count=0,
            )

        operators = {
            entity: OperatorConfig("replace", {"new_value": f"<{entity}>"})
            for entity in self.entities
        }

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators,
        )

        entities_found = list({r.entity_type for r in results})
        return RedactionResult(
            redacted_text=anonymized.text,
            entities_found=entities_found,
            redaction_count=len(results),
        )

    def _redact_regex(self, text: str) -> RedactionResult:
        redacted = text
        entities_found = []
        total_count = 0

        for entity_type, pattern in self._patterns.items():
            matches = pattern.findall(redacted)
            if matches:
                entities_found.append(entity_type)
                total_count += len(matches)
                redacted = pattern.sub(f"<{entity_type}>", redacted)

        return RedactionResult(
            redacted_text=redacted,
            entities_found=entities_found,
            redaction_count=total_count,
        )


# Singleton instance
pii_redactor = PIIRedactor()
