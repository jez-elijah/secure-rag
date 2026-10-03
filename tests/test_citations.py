from secure_rag.generation.citations import validate_citations


def test_single_valid_citation():
    assert validate_citations("The answer is 16 weeks [1].", 5) == ([1], [])


def test_multiple_and_grouped_citations():
    assert validate_citations("A [1] and B [2, 3].", 5) == ([1, 2, 3], [])


def test_nonexistent_source_is_flagged():
    assert validate_citations("Made up claim [7].", 5) == ([], [7])


def test_zero_is_not_a_valid_source():
    assert validate_citations("Odd claim [0].", 5) == ([], [0])


def test_no_citations():
    assert validate_citations("I don't know.", 5) == ([], [])
