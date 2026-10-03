"""Streamlit demo: sign in, then ask questions as your role.

Run from the project root:
    streamlit run app/streamlit_app.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # the pipeline uses paths relative to the project root
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from secure_rag.security.auth import authenticate, issue_token, verify_token  # noqa: E402
from secure_rag.settings import ROLE_ACCESS  # noqa: E402

st.set_page_config(page_title="Secure RAG Assistant", page_icon="🔒")
st.title("🔒 Secure RAG Assistant")


@st.cache_resource(show_spinner="Loading models and document index...")
def load_pipeline():
    from secure_rag import pipeline
    from secure_rag.ingest.indexer import build_index
    from secure_rag.resources import get_collection

    if get_collection().count() == 0:
        build_index()
    return pipeline


def current_user():
    token = st.session_state.get("token")
    return verify_token(token) if token else None


user = current_user()

# ---- Signed-out view -------------------------------------------------------------------
if user is None:
    if st.session_state.get("token"):
        st.warning("Your session expired or is no longer valid. Please sign in again.")
        st.session_state.pop("token", None)
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        found = authenticate(username.strip(), password)
        if found:
            st.session_state["token"] = issue_token(found)
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.caption("Demo accounts are listed in the README.")
    st.stop()

# ---- Signed-in view --------------------------------------------------------------------
rag = load_pipeline()
role = user["role"]

with st.sidebar:
    st.markdown(f"**Signed in as:** {user['username']}")
    st.markdown(f"**Role:** {role}")
    st.markdown("**Can search:** " + ", ".join(ROLE_ACCESS[role]))
    if st.button("Sign out"):
        st.session_state.clear()
        st.rerun()

st.caption(
    "Answers use only documents your role may access. Personal data is redacted "
    "before anything is sent to the LLM."
)

question = st.text_input("Ask a question about Acme's documents")
if st.button("Ask") and question.strip():
    with st.spinner("Searching..."):
        result = rag.ask(question.strip(), user_role=role, redact=True)

    # Escape $ so dollar amounts aren't rendered as math.
    st.markdown(result["answer"].replace("$", "\\$"))

    st.subheader("Sources")
    if result["sources"]:
        for s in result["sources"]:
            st.write(f"[{s['n']}] {s['doc_id']} ({s['title']})")
    else:
        st.write("None cited.")
    if result["invalid_citations"]:
        st.warning(f"The answer cited nonexistent sources: {result['invalid_citations']}")

    with st.expander("What was sent to the LLM (after PII redaction)"):
        st.code(result["outgoing"], language="text")
    with st.expander("Documents searched for this question"):
        st.write(sorted(set(result["retrieved_docs"])))
