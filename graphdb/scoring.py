"""Per (graph, query) score s(g, q).

s(g, q) = 1                                  if g satisfies every path of q
        = alpha * satisfied_paths / |paths|  if g satisfies only some paths of q
        = 0                                  otherwise
"""
from .format import path_labels, satisfies_path, satisfies_query


def prepare_query(query):
    """Precompute the label sets used to skip graphs that can never match."""
    path_label_sets = [path_labels(p) for p in query]
    return query, path_label_sets, set().union(*path_label_sets)


def score(g, prepared, alpha):
    query, path_label_sets, all_labels = prepared
    if all_labels <= g.labels and satisfies_query(g, query):
        return 1.0
    if alpha == 0 or len(query) == 1:
        return 0.0
    hits = sum(1 for p, labels in zip(query, path_label_sets)
               if labels <= g.labels and satisfies_path(g, p))
    return alpha * hits / len(query)
