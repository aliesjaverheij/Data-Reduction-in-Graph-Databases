""" Validates the format of database/query-log files and print dataset statistics.

"""
import argparse
import os
import statistics
import sys
from collections import Counter
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graphdb.format import parse_graph, parse_query, satisfies_path, satisfies_query

GRAPHS = []


def _init(paths):
    global GRAPHS
    GRAPHS = [parse_graph(line) for p in paths for line in open(p) if line.strip()]


def _evaluate(qline):
    q = parse_query(qline)
    full, partial = 0, 0
    for g in GRAPHS:
        if satisfies_query(g, q):
            full += 1
        elif len(q) > 1 and any(satisfies_path(g, p) for p in q):
            partial += 1
    return qline, full, partial


def describe(name, values):
    return (f"{name}: min={min(values)} median={statistics.median(values)} "
            f"mean={statistics.mean(values):.1f} max={max(values)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("databases", nargs="+")
    ap.add_argument("--qlog")
    args = ap.parse_args()

    for path in args.databases:
        nodes, triples = [], []
        for i, line in enumerate(open(path), 1):
            try:
                g = parse_graph(line)
            except ValueError as e:
                sys.exit(f"{path}:{i}: {e}")
            nodes.append(len(g.nodes))
            triples.append(line.count("<"))
        print(f"{os.path.basename(path)}: {len(nodes)} graphs | "
              f"{describe('nodes', nodes)} | {describe('triples', triples)}")

    if not args.qlog:
        return
    lines = [l.strip() for l in open(args.qlog) if l.strip()]
    for i, l in enumerate(lines, 1):
        try:
            parse_query(l)
        except ValueError as e:
            sys.exit(f"{args.qlog}:{i}: {e}")
    freq = Counter(lines)
    print(f"\n{os.path.basename(args.qlog)}: {len(lines)} queries, {len(freq)} distinct")
    print(describe("paths per query", [len(parse_query(l)) for l in freq]))
    print(f"top-5 frequencies: {[c for _, c in freq.most_common(5)]}, "
          f"queries occurring once: {sum(1 for c in freq.values() if c == 1)}")

    with Pool(initializer=_init, initargs=(args.databases,)) as pool:
        n_graphs = len(GRAPHS) or sum(1 for p in args.databases for _ in open(p))
        results = pool.map(_evaluate, list(freq), chunksize=4)
    fulls = [f for _, f, _ in results]
    print(describe("graphs fully satisfying a distinct query", fulls))
    buckets = Counter("0" if f == 0 else "1" if f == 1 else "2-10" if f <= 10 else
                      "11-100" if f <= 100 else "101-1000" if f <= 1000 else ">1000"
                      for f in fulls)
    print("answer-size histogram:",
          {k: buckets[k] for k in ["0", "1", "2-10", "11-100", "101-1000", ">1000"]})
    multi = [(f, p) for q, f, p in results if len(parse_query(q)) > 1]
    print(f"multi-path queries: {len(multi)}, with partially satisfying graphs: "
          f"{sum(1 for _, p in multi if p > 0)}")
    print(f"total graphs: {n_graphs}")


if __name__ == "__main__":
    main()
