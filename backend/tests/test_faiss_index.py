import numpy as np

from recognition.faiss_index import FaissIndex

rng = np.random.default_rng(0)


def unit(v):
    return (v / np.linalg.norm(v)).astype("float32")


def make_index():
    index = FaissIndex()
    vectors = {sid: unit(rng.normal(size=512)) for sid in ("a", "b", "c")}
    for sid, vec in vectors.items():
        index.add_student(sid, vec)
    return index, vectors


def test_search_finds_the_closest_student():
    index, v = make_index()
    assert index.search(v["b"])[0][0] == "b"


def test_search_skips_students_outside_allowed_ids():
    index, v = make_index()
    student_id, _ = index.search(v["b"], allowed_ids={"a", "c"})[0]
    assert student_id in {"a", "c"}


def test_empty_allowed_ids_matches_nobody():
    index, v = make_index()
    assert index.search(v["b"], allowed_ids=set()) == []


def test_top_k_is_respected_when_filtering():
    index, v = make_index()
    results = index.search(v["b"], top_k=2, allowed_ids={"a", "b", "c"})
    assert len(results) == 2
    assert results[0][0] == "b"


def test_empty_index_returns_nothing():
    assert FaissIndex().search(unit(rng.normal(size=512))) == []
