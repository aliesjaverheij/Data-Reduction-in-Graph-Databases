 # Data-Reduction-in-Graph-Databases


**Our dataset (D1) in short.** 
- A social network (persons, real Dutch companies, cities,
universities) with skewed (Zipf) label and value frequencies. 
- Node ids are shared between
graphs, so constant-id queries match several graphs. 
- Six small patterns ("motifs") with ids
9001–9054 are planted in a known set of graphs. They differ in how common they are in the
data and how often they are queried, so we know which graphs a good method should keep. look at: `data/README.txt`.


## The method

**Answer of a query.** Following the assignment, a graph *satisfies* a query if it satisfies
every path in it. The answer of query *q* on database *D* is the set of graphs that fully
satisfy it: **A(q)**. 

Example: for `X.married.Y.city."Utrecht"`, every graph containing a
married couple where the partner has city "Utrecht" is in A(q).

**Query frequency f(q).** How often *q* occurs in the query log. A query asked 20 times
matters more than a query asked once.

**Goal.** Keep k = B·|D| graphs (the set S) such that the answers change as little as possible.

**Diminishing returns.** The first kept answer of a query is the most valuable (without it the
user gets nothing). Every extra answer is still useful, but less. We measure this with:

> **F(S) = Σ_q f(q) · log(1 + c_S(q))**, where c_S(q) = number of graphs in S that answer q

| answers kept | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| extra value of that answer | 0.69 | 0.41 | 0.29 | 0.22 |

This sits between two extremes: "only care whether a query has ≥ 1 answer" and "every answer
is worth the same".

**Greedy.** Start with an empty selection. Repeatedly add the graph that increases F the most
(its *marginal gain*), until k graphs are selected. Because the value of a graph depends on
what is already selected, the gains are recomputed after every choice.

Example (keep 2 graphs): q1 (f = 10) is answered by g1 and g2, q2 (f = 8) by g3.
- Step 1: g1 = 10·0.69 = 6.9, g2 = 6.9, g3 = 8·0.69 = 5.5 → pick g1
- Step 2: g2 = 10·0.41 = 4.1 (second answer of q1), g3 = 5.5 (first answer of q2) → pick g3
- Both queries keep an answer. Ranking the graphs once (top-k) would pick g1 and g2, and q2
  would lose all its answers.

**The 63% guarantee.** F is *monotone submodular* (adding a graph never hurts, and its extra
value never increases as S grows). For such functions greedy always reaches at least
(1 − 1/e) ≈ 63% of the value of the best possible selection (Nemhauser et al., 1978). Finding
that best selection itself is infeasible (too many combinations). 

**Evaluation metrics** (all frequency-weighted over the queries that have ≥ 1 answer in D):
- **fraction**: share of the answers of each query that is kept in D'
- **coverage**: share of queries that still have at least one answer in D'
- **objective**: F(D') / F(D)

---

## Design decisions (with results)

All numbers: our dataset (9,300 graphs, 1,000 queries), B = 10% (930 graphs kept), run
locally. These are preliminary results to support our choices. The full
experiments are for D3/D4.

### Why diminishing returns (log) instead of simply counting answers
If every answer counts the same, the graphs that answer the most popular queries always win,
and less popular queries lose all their answers. If only "≥ 1 answer" counts, extra answers
are worthless. The log is a middle ground. It also makes F submodular, which gives the 63%
guarantee for greedy.

### Comparing greedy with top-k and random

| Method | What it does                                         | Why we compare with it |
|---|------------------------------------------------------|---|
| **greedy** (ours) | Greedy on F with diminishing returns                 | our method |
| **top-k** | scores every graph once on its own, keeps the k best | shows the effect of diminishing returns (same scores, no interaction between graphs) |
| **random** | keeps k random graphs                                | the lower bound|


**Result (B = 10%, α = 0):**

| Method | fraction | coverage | F(D')/F(D) |
|---|---|---|---|
| **greedy** | **0.690** | **1.000** | **0.836** |
| top-k | 0.272 | 0.607 | 0.750 |
| random | 0.150 | 0.612 | 0.588 |

With only 10% of the graphs, greedy keeps at least one answer for **every** answerable query
and on average 69% of the answers. Top-k has worse coverage than random: it keeps many graphs
that answer the same popular queries.

**Planted patterns** (graphs kept / graphs containing the pattern):

| Pattern | greedy | top-k | random |
|---|---|---|---|
| M1 rare in data, often queried | **93/93** | 70/93 | 9/93 |
| M2 common, often queried | 258/939 | 447/939 | 89/939 |
| M3 rare, rarely queried | 27/90 | 14/90 | 6/90 |
| M4 common, never queried | 93/933 | 77/933 | 99/933 |
| M5 medium, medium queried | 103/340 | 64/340 | 33/340 |
| M6 hub with attributes, often queried | 122/262 | 84/262 | 19/262 |

Greedy keeps all rare-but-popular graphs (M1). It keeps a part of the common-and-popular ones
(M2), because of diminishing returns. It treats never-queried graphs (M4) like random does.

### Why α = 0 (only full matches count)
The assignment defines that a graph satisfies a query only if it satisfies *every* path, a
graph that satisfies some paths only "partially satisfies" it. We therefore treat only full
matches as answers. Our code has a parameter α that gives partial credit,
s = α · (satisfied paths / paths). We tested it:

| α | fraction | coverage |
|---|---|---|
| **0 (default)** | **0.690** | **1.000** |
| 0.1 | 0.679 | 0.989 |
| 0.3 | 0.671 | 0.984 |
| 0.5 | 0.669 | 0.984 |
| 1.0 | 0.663 | 0.979 |

The larger α, the more budget goes to graphs that only partially answer queries, so fewer full
answers are kept. Note: these metrics only count full answers, so α = 0 is favoured by
definition. α > 0 only makes sense if partial answers are also considered useful.

### Why B = 10% in these tests
B is an input of the program (chosen by the user). We used 10% because it is a strong
reduction where the differences between methods are clear. In the experiments for D4 we will
vary B (e.g. 1%, 5%, 10%, 25%, 50%).

### Spark design choices
- **Graphs are the unit of parallelism.** Each graph is one record. Matching a graph against
  the queries does not need other graphs, so this step runs fully in parallel with no shuffle.
- **Queries are broadcast.** The query log is small, so it is parsed once on the driver and
  sent once to every executor, together with the set of labels each query needs. A graph that
  misses one of those labels is skipped without traversing it.
- **Sparse score matrix.** Per graph we only keep the queries it answers, and cache this RDD,
  because selection and evaluation both reuse it.
- **Selection on the driver.** Greedy is sequential (each step depends on the previous one).
  The sparse matrix is small, so we collect it and run greedy on the driver. 

---

## References

- Nemhauser, G. L., Wolsey, L. A., & Fisher, M. L. (1978). An analysis of approximations for
  maximizing submodular set functions—I. *Mathematical Programming*, 14(1), 265–294.

