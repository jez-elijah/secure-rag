"""Show exactly what would be sent to the LLM for a question (with redaction on).

Usage (from the project root):
    python eval/debug_redaction.py finance "Who approved Priya Raman's reimbursement?"
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from secure_rag.pipeline import ask  # noqa: E402

role, question = sys.argv[1], " ".join(sys.argv[2:])
result = ask(question, user_role=role, redact=True)

print("=== SENT TO THE LLM ===")
print(result["outgoing"])
print("\n=== FINAL ANSWER (after restore) ===")
print(result["answer"])
