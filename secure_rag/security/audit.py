"""Append-only audit log of who asked what and which documents were retrieved."""
import json
from datetime import datetime, timezone

from secure_rag.settings import AUDIT_LOG


def audit(user_role, question, metas, redacted):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": user_role,
        "question": question,  # already redacted when redaction is on, so logs hold no PII
        "retrieved": [m["doc_id"] for m in metas],
        "redacted": redacted,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
