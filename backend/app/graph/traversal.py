"""Bounded breadth-first path enumeration and path scoring."""

import math

from app.graph.store import GraphStore, Relation

SEED_LINK_BONUS = 0.1

Path = list[tuple[Relation, bool]]  # (edge, traversed source -> target)


def _end(path: Path, start: str) -> str:
    node = start
    for rel, forward in path:
        node = rel.target if forward else rel.source
    return node


def enumerate_paths(graph: GraphStore, seed_ids: list[str], max_hops: int, max_degree: int, max_paths: int) -> list[Path]:
    """All simple paths of 1..max_hops edges starting at a seed. Non-seed nodes with
    degree above max_degree end a path but are not expanded. Stops at max_paths."""
    paths: list[Path] = []
    # frontier entries: (path, visited nodes, current node)
    frontier: list[tuple[Path, frozenset[str], str]] = [([], frozenset([s]), s) for s in dict.fromkeys(seed_ids)]
    seeds = set(seed_ids)
    for _ in range(max_hops):
        current = {node for _, _, node in frontier}
        degrees = {e.id: e.degree for e in graph.get_entities(sorted(current))}
        expandable = {n for n in current if n in seeds or degrees.get(n, 0) <= max_degree}
        if not expandable:
            break
        edges_by_node: dict[str, list[Relation]] = {n: [] for n in expandable}
        for rel in graph.neighbors(sorted(expandable)):
            for n in (rel.source, rel.target):
                if n in edges_by_node:
                    edges_by_node[n].append(rel)
        next_frontier = []
        for path, visited, node in frontier:
            for rel in edges_by_node.get(node, []):
                forward = rel.source == node
                other = rel.target if forward else rel.source
                if other in visited:
                    continue
                new_path = [*path, (rel, forward)]
                paths.append(new_path)
                if len(paths) >= max_paths:
                    return paths
                next_frontier.append((new_path, visited | {other}, other))
        frontier = next_frontier
    return paths


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def score_paths(
    paths: list[Path],
    query_vec: list[float],
    edge_vecs: dict[str, list[float]],
    hop_decay: float,
    seed_ids: list[str],
    min_score: float,
    top_k: int,
) -> list[tuple[Path, float]]:
    """score = mean(cos(query, edge fact)) * hop_decay^(hops-1), +0.1 if the path ends
    on a different seed than it started from."""
    seeds = set(seed_ids)
    scored = []
    for path in paths:
        sims = [_cos(query_vec, edge_vecs[rel.key]) for rel, _ in path]
        score = (sum(sims) / len(sims)) * hop_decay ** (len(path) - 1)
        first, forward = path[0]
        start = first.source if forward else first.target
        end = _end(path, start)
        if end in seeds and end != start:
            score += SEED_LINK_BONUS
        if score >= min_score:
            scored.append((path, score))
    scored.sort(key=lambda item: -item[1])
    return scored[:top_k]
