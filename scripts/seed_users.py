"""Create the demo users (one per role). Run from the project root:

    python scripts/seed_users.py

Demo credentials only. Never use a predictable password pattern outside a demo.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from secure_rag.security.auth import create_user  # noqa: E402

DEMO_USERS = [
    ("alice", "employee"),
    ("hana", "hr"),
    ("fiona", "finance"),
    ("evan", "engineering"),
    ("admin", "admin"),
]

print(f"{'username':<10} {'role':<12} password")
for username, role in DEMO_USERS:
    password = f"demo-{username}-123"
    create_user(username, password, role)
    print(f"{username:<10} {role:<12} {password}")
