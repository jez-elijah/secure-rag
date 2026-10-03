"""Validate that every [n] citation in an answer maps to a retrieved chunk."""
import re


def validate_citations(answer, n_chunks):
    """Return (valid, invalid) sorted lists of cited source numbers."""
    cited = set()
    for group in re.findall(r"\[([\d,\s]+)\]", answer):
        cited.update(int(n) for n in re.split(r"[,\s]+", group.strip()) if n)
    valid = sorted(n for n in cited if 1 <= n <= n_chunks)
    invalid = sorted(n for n in cited if n not in valid)
    return valid, invalid
