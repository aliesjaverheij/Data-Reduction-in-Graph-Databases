"""Data reduction for graph databases in Apache Spark.

Selects B * |D| graphs from the database that best serve the query log, using the
diminishing-returns objective F(S) = sum_q f(q) * log(1 + c_S(q)) (see graphdb/selection.py).

Usage:
  python reduce_spark.py --db "data/Database19_*.txt" --qlog data/QLog19.txt --budget 0.1
  options: --method greedy|topk|random  --alpha 0.0  --out results/run1

Pipeline:
  1. textFile + zipWithIndex          -> (graph id, raw line)
  2. query log parsed on the driver   -> distinct queries with frequency f(q), broadcast
  3. mapPartitions: parse graphs and score every query
                                      -> (graph id, [(query id, s(g, q))]), cached
  4. selection
       greedy : collect the sparse score matrix, lazy greedy on the driver
       topk   : stand-alone value of each graph, takeOrdered (baseline)
       random : random sample (baseline)
  5. write the reduced database, the selected ids and the evaluation metrics
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter

from pyspark.sql import SparkSession

from graphdb.format import parse_graph, parse_query
from graphdb.scoring import prepare_query, score
from graphdb.selection import evaluate, fill_up, gain, lazy_greedy

HERE = os.path.dirname(os.path.abspath(__file__))


def ship_package(sc):
    """Make the graphdb package importable on the executors."""
    tmp = tempfile.mkdtemp()
    archive = shutil.make_archive(os.path.join(tmp, "graphdb"), "zip", HERE, "graphdb")
    sc.addPyFile(archive)


def score_partition(rows, queries_bc, alpha):
    queries = queries_bc.value
    for gid, line in rows:
        g = parse_graph(line)
        entries = []
        for qid, prepared in enumerate(queries):
            s = score(g, prepared, alpha)
            if s > 0:
                entries.append((qid, s))
        yield gid, entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="database file(s), glob allowed")
    ap.add_argument("--qlog", required=True)
    ap.add_argument("--budget", type=float, required=True, help="B in [0, 1]")
    ap.add_argument("--method", default="greedy", choices=["greedy", "topk", "random"])
    ap.add_argument("--alpha", type=float, default=0.0,
                    help="weight of partial matches (0 = only full matches count as answers)")
    ap.add_argument("--partitions", type=int, default=0, help="0 = number of cores")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results/run")
    ap.add_argument("--master", default="local[*]")
    args = ap.parse_args()

    db_files = sorted(f for pattern in args.db.split(",") for f in glob.glob(pattern))
    if not db_files:
        sys.exit(f"no database files match {args.db}")
    spark = (SparkSession.builder.appName("graph-data-reduction").master(args.master)
             .config("spark.driver.memory", "4g").getOrCreate())
    sc = spark.sparkContext
    sc.setLogLevel("ERROR")
    ship_package(sc)
    t0 = time.time()

    # 1. graphs with a global id (line number over all files, in file order)
    lines = sc.textFile(",".join(db_files)).filter(lambda l: l.strip())
    graphs = lines.zipWithIndex().map(lambda x: (x[1], x[0]))  # ids before repartitioning
    graphs = graphs.repartition(args.partitions or sc.defaultParallelism)
    graphs.cache()
    n = graphs.count()
    k = round(args.budget * n)

    # 2. query log: distinct queries weighted by frequency, broadcast to the executors
    freq_by_text = Counter(l.strip() for l in open(args.qlog) if l.strip())
    query_texts = list(freq_by_text)
    freq = [freq_by_text[q] for q in query_texts]
    queries_bc = sc.broadcast([prepare_query(parse_query(q)) for q in query_texts])
    freq_bc = sc.broadcast(freq)

    # 3. sparse score matrix
    alpha = args.alpha
    scores = graphs.mapPartitions(lambda rows: score_partition(rows, queries_bc, alpha))
    scores.cache()
    scores.count()
    t_score = time.time() - t0

    # 4. selection
    t_sel = time.time()
    if args.method == "greedy":
        selected = lazy_greedy(dict(scores.collect()), freq, k)
    elif args.method == "topk":
        selected = [g for g, _ in scores.map(lambda x: (x[0], gain(x[1], freq_bc.value, {})))
                    .filter(lambda x: x[1] > 0)
                    .takeOrdered(k, key=lambda x: (-x[1], x[0]))]
    else:
        selected = graphs.keys().takeSample(False, k, seed=args.seed)
    selected = fill_up(selected, range(n), k, args.seed)
    t_sel = time.time() - t_sel
    t_total = time.time() - t0

    # 5. output
    os.makedirs(args.out, exist_ok=True)
    sel_bc = sc.broadcast(set(selected))
    reduced = graphs.filter(lambda x: x[0] in sel_bc.value).sortByKey().values().collect()
    with open(os.path.join(args.out, "DatabaseReduced.txt"), "w") as f:
        f.write("\n".join(reduced) + "\n")
    with open(os.path.join(args.out, "selected_ids.txt"), "w") as f:
        f.write("\n".join(map(str, sorted(selected))) + "\n")

    metrics = evaluate(dict(scores.collect()), freq, selected)
    metrics.update(method=args.method, budget=args.budget, alpha=alpha, graphs=n,
                   selected=len(selected), distinct_queries=len(query_texts),
                   partitions=graphs.getNumPartitions(),
                   seconds_scoring=round(t_score, 2), seconds_selection=round(t_sel, 2),
                   seconds_total=round(t_total, 2))
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    print(json.dumps(metrics, indent=1))
    spark.stop()


if __name__ == "__main__":
    main()
