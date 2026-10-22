"""Graph selection with diminishing returns, plus evaluation metrics.

Objective for a selection S:
    F(S) = sum_q f(q) * log(1 + c_S(q)),   c_S(q) = sum_{g in S} s(g, q)

F is monotone submodular, so greedy selection is a (1 - 1/e)-approximation.
`entries` maps graph id -> [(query id, s(g, q))] with s > 0 (sparse score matrix).
"""
import heapq
import math
import random


def gain(entries_g, freq, cov):
    return sum(freq[q] * (math.log1p(cov.get(q, 0.0) + s) - math.log1p(cov.get(q, 0.0)))
               for q, s in entries_g)


def lazy_greedy(entries, freq, k, candidates=None):
    """Greedy maximisation of F with lazy evaluation (CELF).

    Gains only decrease as the selection grows, so a stale gain is an upper bound:
    we only recompute the graph at the top of the heap.
    """
    candidates = list(entries) if candidates is None else list(candidates)
    cov, selected = {}, []
    heap = [(-gain(entries[g], freq, cov), g, 0) for g in candidates]
    heapq.heapify(heap)
    while heap and len(selected) < k:
        neg, g, stamp = heapq.heappop(heap)
        if stamp == len(selected):
            selected.append(g)
            for q, s in entries[g]:
                cov[q] = cov.get(q, 0.0) + s
        else:
            heapq.heappush(heap, (-gain(entries[g], freq, cov), g, len(selected)))
    return selected


def top_k(entries, freq, k):
    """Baseline: rank graphs by their stand-alone value, no interaction between them."""
    value = {g: gain(e, freq, {}) for g, e in entries.items()}
    return sorted(value, key=lambda g: (-value[g], g))[:k]


def fill_up(selected, all_ids, k, seed=0):
    """Graphs that match no query have zero value; fill a remaining budget randomly."""
    chosen = set(selected)
    rest = [g for g in all_ids if g not in chosen]
    random.Random(seed).shuffle(rest)
    return list(selected) + rest[:k - len(selected)]


def evaluate(entries, freq, selected):
    """Compare query answers on D' (= selected) with those on D.

    fraction : frequency-weighted share of full answers that is kept
    coverage : frequency-weighted share of answerable queries that keeps >= 1 answer
    objective: F(D') / F(D)
    """
    sel = set(selected)
    full_all, full_kept, cov_all, cov_kept = {}, {}, {}, {}
    for g, e in entries.items():
        for q, s in e:
            cov_all[q] = cov_all.get(q, 0.0) + s
            if s == 1.0:
                full_all[q] = full_all.get(q, 0) + 1
            if g in sel:
                cov_kept[q] = cov_kept.get(q, 0.0) + s
                if s == 1.0:
                    full_kept[q] = full_kept.get(q, 0) + 1
    answerable = [q for q in full_all]
    total_f = sum(freq[q] for q in answerable) or 1
    fraction = sum(freq[q] * full_kept.get(q, 0) / full_all[q] for q in answerable) / total_f
    coverage = sum(freq[q] for q in answerable if full_kept.get(q, 0) > 0) / total_f
    f_all = sum(freq[q] * math.log1p(c) for q, c in cov_all.items())
    f_kept = sum(freq[q] * math.log1p(c) for q, c in cov_kept.items())
    return {"fraction": fraction, "coverage": coverage,
            "objective": f_kept / f_all if f_all else 1.0}
