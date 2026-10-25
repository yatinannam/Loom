from app.graph.memory_store import InMemoryGraphStore
from app.graph.store import Entity, Mention, Relation
from app.graph.traversal import enumerate_paths, score_paths

M = Mention("d:0", "d", "d.md", None)


def build(edges):
    g = InMemoryGraphStore()
    for s, t in edges:
        for n in (s, t):
            g.upsert_entity(Entity(n, n.upper(), "OTHER"), M)
        g.upsert_relation(s, t, "REL", M, f"{s} rel {t}", 0.9)
    g.recompute_degrees()
    return g


def nodes(path, start):
    seq = [start]
    for rel, forward in path:
        seq.append(rel.target if forward else rel.source)
    return seq


def test_hop_bound():
    g = build([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f")])
    paths = enumerate_paths(g, ["a"], max_hops=3, max_degree=50, max_paths=100)
    assert max(len(p) for p in paths) == 3
    assert ["a", "b", "c", "d"] in [nodes(p, "a") for p in paths]


def test_backward_edges_followed():
    g = build([("b", "a")])
    paths = enumerate_paths(g, ["a"], max_hops=2, max_degree=50, max_paths=100)
    assert len(paths) == 1
    rel, forward = paths[0][0]
    assert forward is False
    assert nodes(paths[0], "a") == ["a", "b"]


def test_hub_is_endpoint_but_not_expanded():
    g = build([("s", "hub")] + [("hub", f"x{i}") for i in range(10)])
    paths = enumerate_paths(g, ["s"], max_hops=3, max_degree=5, max_paths=100)
    assert [nodes(p, "s") for p in paths] == [["s", "hub"]]


def test_high_degree_seed_still_expanded():
    g = build([("hub", f"x{i}") for i in range(10)])
    paths = enumerate_paths(g, ["hub"], max_hops=2, max_degree=5, max_paths=100)
    assert len(paths) == 10


def test_cycles_not_revisited():
    g = build([("a", "b"), ("b", "c"), ("c", "a")])
    paths = enumerate_paths(g, ["a"], max_hops=4, max_degree=50, max_paths=100)
    for p in paths:
        seq = nodes(p, "a")
        assert len(seq) == len(set(seq))


def test_max_paths_caps_output():
    g = build([("a", f"x{i}") for i in range(30)])
    assert len(enumerate_paths(g, ["a"], max_hops=2, max_degree=100, max_paths=7)) == 7


def rel(s, t):
    return Relation(s, t, "REL", [f"{s}{t}:0"], ["d"], ["e"], 0.9)


def test_relevant_path_outranks_irrelevant():
    good = [(rel("a", "b"), True)]
    bad = [(rel("a", "c"), True)]
    vecs = {"a|REL|b": [1.0, 0.0], "a|REL|c": [0.0, 1.0]}
    ranked = score_paths([bad, good], [1.0, 0.0], vecs, hop_decay=0.85, seed_ids=["a"], min_score=0.0, top_k=5)
    assert ranked[0][0] is good
    assert ranked[0][1] > ranked[1][1]


def test_longer_path_decayed_and_min_score_filters():
    short = [(rel("a", "b"), True)]
    long = [(rel("a", "b"), True), (rel("b", "c"), True)]
    vecs = {"a|REL|b": [1.0, 0.0], "b|REL|c": [1.0, 0.0]}
    ranked = score_paths([long, short], [1.0, 0.0], vecs, hop_decay=0.5, seed_ids=["a"], min_score=0.0, top_k=5)
    assert ranked[0][0] is short
    assert abs(ranked[1][1] - 0.5) < 1e-9
    assert score_paths([long], [1.0, 0.0], vecs, 0.5, ["a"], min_score=0.6, top_k=5) == []


def test_path_connecting_two_seeds_gets_bonus():
    p = [(rel("a", "b"), True)]
    vecs = {"a|REL|b": [1.0, 0.0]}
    alone = score_paths([p], [0.5, 0.5], vecs, 0.85, ["a"], 0.0, 5)[0][1]
    linked = score_paths([p], [0.5, 0.5], vecs, 0.85, ["a", "b"], 0.0, 5)[0][1]
    assert abs(linked - alone - 0.1) < 1e-9
