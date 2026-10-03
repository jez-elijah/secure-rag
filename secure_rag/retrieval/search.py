"""Vector search with role-based filtering applied at query time."""
from secure_rag import resources
from secure_rag.settings import K, ROLE_ACCESS


def retrieve(question, k=K, user_role=None):
    """Top-k chunks. With a user_role, the search is limited to departments that role may see,
    so restricted chunks are never returned and can never reach the model."""
    where = None
    if user_role is not None:
        if user_role not in ROLE_ACCESS:
            raise ValueError(f"Unknown role: {user_role}")
        where = {"department": {"$in": ROLE_ACCESS[user_role]}}
    q_emb = resources.embedder.encode([question], normalize_embeddings=True).tolist()
    res = resources.get_collection().query(query_embeddings=q_emb, n_results=k, where=where)
    return res["documents"][0], res["metadatas"][0]
