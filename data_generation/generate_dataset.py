"""Generates the D1 graph database (one file per graph shape) and query log.

Design (see README):
  * social-network domain: persons, companies, cities, universities
  * skewed (Zipf) label / attribute value frequencies
  * node ids are drawn from a shared id space, so the same id occurs in many graphs
    and constant-id queries match more than one graph
  * motifs with fixed ids give a known ground truth: motifs differ in how
    often they occur in the data and how often they are queried
  * query log mixes constants/variables, path lengths, single/multi-path queries,
    partially satisfiable and unsatisfiable queries, and repeats

"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graphdb.format import Graph

TYPES = ["person", "company", "city", "university"]
TYPE_WEIGHTS = [0.70, 0.12, 0.10, 0.08]

# (source type, destination type) -> labels, ordered from frequent to rare
EDGE_LABELS = {
    ("person", "person"): ["knows", "friendOf", "follows", "colleagueOf", "married",
                           "parentOf", "siblingOf", "mentors", "blocked"],
    ("person", "company"): ["worksAt", "follows", "manages", "founded", "investsIn"],
    ("person", "city"): ["livesIn", "bornIn", "visited"],
    ("person", "university"): ["studiesAt", "graduatedFrom", "teachesAt"],
    ("company", "company"): ["partnerOf", "competitorOf", "acquired"],
    ("company", "city"): ["locatedIn"],
    ("company", "person"): ["employs"],
    ("company", "university"): ["sponsors"],
    ("university", "city"): ["locatedIn"],
    ("university", "company"): ["partnerOf"],
    ("city", "city"): ["connectedTo", "twinnedWith"],
    ("city", "person"): ["hasResident", "mayor"],
    ("city", "company"): ["hosts"],
    ("city", "university"): ["hosts"],
    ("university", "person"): ["employs"],
}

FIRST_NAMES = ["Anna", "Daan", "Emma", "Sem", "Julia", "Lucas", "Mila", "Noah", "Sophie",
               "Levi", "Tess", "Finn", "Sara", "Jesse", "Lotte", "Bram", "Eva", "Thijs",
               "Fleur", "Ruben", "Iris", "Milan", "Lisa", "Jayden", "Zoe", "Mohammed",
               "Yara", "Adam", "Nina", "Liam", "Fatima", "Omar", "Mei", "Wei", "Priya"]

CITIES = ["Amsterdam", "Rotterdam", "Utrecht", "DenHaag", "Eindhoven", "Groningen",
          "Tilburg", "Almere", "Breda", "Nijmegen", "Leiden", "Delft", "Maastricht",
          "Zwolle", "Arnhem", "Haarlem", "Amersfoort", "Enschede", "Berlin", "Paris",
          "London", "Madrid", "Rome", "Vienna", "Lisbon", "Oslo", "Athens", "Prague"]

COUNTRIES = {"Berlin": "Germany", "Paris": "France", "London": "UK", "Madrid": "Spain",
             "Rome": "Italy", "Vienna": "Austria", "Lisbon": "Portugal",
             "Oslo": "Norway", "Athens": "Greece", "Prague": "Czechia"}

JOBS = ["engineer", "teacher", "nurse", "student", "developer", "designer", "lawyer",
        "doctor", "researcher", "manager", "chef", "artist", "farmer", "pilot", "judge"]

# name -> (sector, founding year), ordered from frequent to rare
COMPANIES = {
    "Philips": ("health", 1891), "ASML": ("tech", 1984), "Shell": ("energy", 1907),
    "Heineken": ("food", 1864), "ING": ("finance", 1991), "Ahold": ("retail", 1887),
    "KPN": ("tech", 1989), "Unilever": ("food", 1929), "Rabobank": ("finance", 1972),
    "KLM": ("logistics", 1919), "Booking": ("tech", 1996), "Jumbo": ("retail", 1921),
    "DSM": ("health", 1902), "Coolblue": ("retail", 1999), "Adyen": ("finance", 2006),
}
UNIVERSITIES = ["UU", "UvA", "VU", "TUD", "TUE", "RUG", "EUR", "LEI", "RU", "UT", "WUR",
                "TiU", "UM", "OU"]

GENDERS = ["female", "male", "nonbinary"]


def zipf_choice(rng, items, s=1.2):
    weights = [1.0 / (i + 1) ** s for i in range(len(items))]
    return rng.choices(items, weights=weights)[0]


def random_attrs(rng, ntype, richness):
    attrs = [("type", ntype)]
    if ntype == "person":
        opts = [("name", lambda: zipf_choice(rng, FIRST_NAMES, 0.8)),
                ("age", lambda: str(int(rng.triangular(16, 90, 30)))),
                ("city", lambda: zipf_choice(rng, CITIES)),
                ("job", lambda: zipf_choice(rng, JOBS)),
                ("gender", lambda: rng.choice(GENDERS))]
    elif ntype == "company":
        c = zipf_choice(rng, list(COMPANIES))
        sector, year = COMPANIES[c]
        opts = [("name", lambda: c),
                ("sector", lambda: sector),
                ("founded", lambda: str(year))]
    elif ntype == "city":
        c = zipf_choice(rng, CITIES)
        opts = [("name", lambda: c),
                ("country", lambda: COUNTRIES.get(c, "Netherlands")),
                ("population", lambda: str(rng.randint(10, 3000) * 1000))]
    else:
        opts = [("name", lambda: zipf_choice(rng, UNIVERSITIES)),
                ("ranking", lambda: str(rng.randint(1, 500)))]
    for name, f in opts:
        if rng.random() < richness:
            attrs.append((name, f()))
    return attrs


def edge_label(rng, st, dt):
    labels = EDGE_LABELS.get((st, dt))
    if not labels:
        return None
    return zipf_choice(rng, labels)


def shape_random(rng, n, avg_deg):
    pairs = set()
    m = max(n - 1, int(n * avg_deg / 2))
    for j in range(1, n):  # spanning tree keeps the graph connected
        pairs.add((rng.randrange(j), j))
    while len(pairs) < m:
        i, j = rng.randrange(n), rng.randrange(n)
        if i != j:
            pairs.add((i, j))
    return list(pairs)


def shape_preferential(rng, n, k=2):
    pairs, targets = [], [0]
    for j in range(1, n):
        for t in set(rng.choice(targets) for _ in range(min(k, j))):
            pairs.append((j, t) if rng.random() < 0.5 else (t, j))
            targets += [t, j]
    return pairs


def shape_star(rng, n):
    return [((0, j) if rng.random() < 0.8 else (j, 0)) for j in range(1, n)]


def shape_line(rng, n):
    return [(j, j + 1) for j in range(n - 1)]


def shape_cycle(rng, n):
    pairs = [(j, (j + 1) % n) for j in range(n)]
    for _ in range(rng.choice([0, 0, 0, 1, 2])):  # occasional chords
        i, j = rng.sample(range(n), 2)
        pairs.append((i, j))
    return pairs


def shape_tree(rng, n):
    branching = rng.choice([2, 3, 4])
    return [((j - 1) // branching, j) for j in range(1, n)]


# data_rate: fraction of graphs (of the allowed shapes) that get the motif planted.
# query_weight: relative share of motif queries in the log.

MOTIFS = [
    dict(name="M1_rare_hot", data_rate=0.01, query_weight=10,
         edges=[(9001, "married", 9002), (9002, "worksAt", 9003), (9003, "locatedIn", 9004)],
         attrs=[(9001, "type", "person"), (9002, "type", "person"), (9003, "type", "company"),
                (9003, "name", "Adyen"), (9004, "type", "city"), (9004, "name", "Utrecht")]),
    dict(name="M2_common_hot", data_rate=0.10, query_weight=8,
         edges=[(9011, "knows", 9012), (9012, "knows", 9013)],
         attrs=[(9011, "type", "person"), (9012, "type", "person"), (9013, "type", "person"),
                (9013, "job", "pilot")]),
    dict(name="M3_rare_cold", data_rate=0.01, query_weight=1,
         edges=[(9021, "mentors", 9022), (9022, "studiesAt", 9023)],
         attrs=[(9021, "type", "person"), (9022, "type", "person"),
                (9023, "type", "university"), (9023, "name", "UU")]),
    dict(name="M4_common_cold", data_rate=0.10, query_weight=0,
         edges=[(9031, "follows", 9032)],
         attrs=[(9031, "type", "person"), (9032, "type", "person")]),
    dict(name="M5_medium_warm", data_rate=0.04, query_weight=4,
         edges=[(9041, "founded", 9042), (9042, "partnerOf", 9043), (9043, "locatedIn", 9044)],
         attrs=[(9041, "type", "person"), (9041, "city", "Amsterdam"),
                (9042, "type", "company"), (9042, "sector", "tech"),
                (9043, "type", "company"), (9044, "type", "city"), (9044, "name", "Berlin")]),
    dict(name="M6_hub_attr", data_rate=0.03, query_weight=5,
         edges=[(9051, "employs", 9052), (9051, "employs", 9053), (9051, "employs", 9054)],
         attrs=[(9051, "type", "company"), (9051, "sector", "health"),
                (9052, "job", "nurse"), (9053, "job", "doctor"), (9054, "job", "nurse")]),
]


def plant_motif(g, motif, rng, ids):
    for s, l, d in motif["edges"]:
        g.add_edge(s, l, d)
    for n, a, v in motif["attrs"]:
        if (a, v) not in g.attrs.get(n, []):
            g.add_attr(n, a, v)
    anchor = rng.choice(ids)
    first = motif["edges"][0][0]
    g.add_edge(anchor, "knows" if rng.random() < 0.5 else "follows", first)


def build_graph(rng, n, pairs, id_space, richness):
    ids = rng.sample(range(1, id_space + 1), n)
    types = rng.choices(TYPES, weights=TYPE_WEIGHTS, k=n)
    g = Graph()
    for i, j in pairs:
        st, dt = types[i], types[j]
        lab = edge_label(rng, st, dt)
        if lab is None:  # no meaningful relation: flip direction or fall back
            lab = edge_label(rng, dt, st)
            if lab is None:
                lab = "relatedTo"
            else:
                i, j = j, i
        g.add_edge(ids[i], lab, ids[j])
    for idx, nid in enumerate(ids):
        for a, v in random_attrs(rng, types[idx], richness):
            g.add_attr(nid, a, v)
    return g, ids


SHAPES = {
    # file suffix: (description, count, size range, shape fn, id space, attr richness)
    1: ("small", 3000, (3, 10), lambda r, n: shape_random(r, n, 2.5), 60, 0.6),
    2: ("large", 300, (100, 400), lambda r, n: shape_preferential(r, n), 2000, 0.4),
    3: ("star", 1500, (5, 60), shape_star, 500, 0.5),
    4: ("line", 1500, (4, 40), shape_line, 500, 0.5),
    5: ("cycle", 1500, (3, 30), shape_cycle, 500, 0.5),
    6: ("tree", 1500, (5, 80), shape_tree, 500, 0.5),
}


def generate_database(rng, scale):
    files, truth = {}, {m["name"]: [] for m in MOTIFS}
    gid = 0
    for idx, (desc, count, (lo, hi), fn, id_space, rich) in SHAPES.items():
        graphs = []
        for _ in range(max(1, int(count * scale))):
            n = rng.randint(lo, hi)
            g, ids = build_graph(rng, n, fn(rng, n), id_space, rich)
            for m in MOTIFS:
                if rng.random() < m["data_rate"]:
                    plant_motif(g, m, rng, ids)
                    truth[m["name"]].append(gid)
            graphs.append((gid, g))
            gid += 1
        files[idx] = graphs
    return files, truth


VARS = ["X", "Y", "Z", "W", "V", "U"]  # "A" is reserved for attribute values


def random_walk(rng, g, start, hops):
    comps, node = [start], start
    for _ in range(hops):
        out = g.out.get(node)
        if not out:
            break
        lab, nxt = rng.choice(out)
        comps += [lab, nxt]
        node = nxt
    return comps


def end_with_attr(rng, g, comps):
    attrs = [a for a in g.attrs.get(comps[-1], []) if a[0] != "type"] or g.attrs.get(comps[-1])
    if attrs:
        a, v = rng.choice(attrs)
        comps = comps + [a, f'"{v}"']
    return comps


def generalise(rng, comps, var_prob, var_names):
    """ Replace node ids by variables (consistent within the path / query)."""
    out = []
    for i, c in enumerate(comps):
        if i % 2 == 0 and isinstance(c, int) and rng.random() < var_prob:
            if c not in var_names:
                var_names[c] = VARS[len(var_names) % len(VARS)] + \
                    ("" if len(var_names) < len(VARS) else str(len(var_names) // len(VARS)))
            out.append(var_names[c])
        else:
            out.append(c)
    return out


def comps_to_str(comps):
    return ".".join(str(c) for c in comps)


def walk_path(rng, g, start=None, hops=None, var_prob=0.0, var_names=None, attr_end=0.3,
              label_end=0.05):
    start = start if start is not None else rng.choice(sorted(g.nodes))
    hops = hops if hops is not None else rng.choice([1, 1, 2, 2, 2, 3, 3, 4])
    comps = random_walk(rng, g, start, hops)
    if rng.random() < attr_end:
        comps = end_with_attr(rng, g, comps)
        if len(comps) >= 3 and rng.random() < 0.2:
            comps[-1] = "A"  # attribute value as variable, e.g. 5.married.X.city.A
    elif len(comps) >= 3 and rng.random() < label_end:
        comps = comps[:-1]  # path ending with an edge label
    comps = generalise(rng, comps, var_prob, var_names if var_names is not None else {})
    return comps_to_str(comps) if len(comps) > 1 else None


def motif_query(rng, motif):
    """ A query over a planted motif, sometimes generalised with variables."""
    g = Graph()
    for s, l, d in motif["edges"]:
        g.add_edge(s, l, d)
    for n, a, v in motif["attrs"]:
        g.add_attr(n, a, v)
    var_names = {}
    var_prob = rng.choice([0.0, 0.0, 0.3, 0.6])
    root = motif["edges"][0][0]
    paths = {walk_path(rng, g, start=root, hops=len(motif["edges"]), var_prob=var_prob,
                       var_names=var_names, attr_end=0.5, label_end=0.0)}
    if rng.random() < 0.4:  # add a second path over the motif
        s = rng.choice(sorted(g.out))
        paths.add(walk_path(rng, g, start=s, hops=2, var_prob=var_prob, var_names=var_names,
                            attr_end=0.7))
    return ",".join(p for p in paths if p)


def organic_query(rng, g, kind):
    var_names = {}
    if kind == "exact":
        paths = [walk_path(rng, g)]
    elif kind == "variable":
        paths = [walk_path(rng, g, var_prob=0.7, var_names=var_names)]
    elif kind == "multi":  # several paths from one start node, sharing a variable
        start = rng.choice(sorted(g.out)) if g.out else rng.choice(sorted(g.nodes))
        vp = rng.choice([0.0, 0.5, 1.0])
        paths = [walk_path(rng, g, start=start, var_prob=vp, var_names=var_names)
                 for _ in range(rng.randint(2, 4))]
    elif kind == "attribute":  # e.g. X.livesIn.Y.name."Utrecht"
        paths = [walk_path(rng, g, hops=rng.choice([0, 1]), var_prob=1.0,
                           var_names=var_names, attr_end=1.0)]
    else:
        raise ValueError(kind)
    paths = list(dict.fromkeys(p for p in paths if p))
    return ",".join(paths) if paths else None


def general_query(rng):
    """ Very broad queries matching a large part of the database."""
    lab = zipf_choice(rng, ["knows", "worksAt", "livesIn", "friendOf", "follows", "locatedIn"])
    a = zipf_choice(rng, ["city", "job", "sector", "name"])
    return rng.choice([
        f"X.{lab}.Y",
        f"X.{lab}.Y.{lab}.Z",
        f"X.{a}",
        f'X.type."{rng.choice(TYPES)}"',
        f"X.{lab}.Y.{a}.Z",
    ])


def unsatisfiable_query(rng):
    lab = rng.choice(["teleportsTo", "hates", "ownsPet", "marriedTo"])  # not in vocabulary
    return rng.choice([
        f"X.{lab}.Y",
        f"{rng.randint(1, 60)}.married.{rng.randint(1, 60)}.married.{rng.randint(1, 60)}",
        f'X.city."Atlantis"',
        f'X.mayor.Y.job."astronaut"',
    ])


def partial_query(rng, g1, g2):
    """Paths taken from two different graphs: most graphs satisfy only part of it."""
    p1, p2 = walk_path(rng, g1), walk_path(rng, g2)
    return ",".join(dict.fromkeys(p for p in (p1, p2) if p)) or None


def generate_query_log(rng, files, n_distinct, n_log):
    all_graphs = [g for graphs in files.values() for _, g in graphs]
    # a "hot" subset of graphs that receives most organic queries (workload skew)
    hot = rng.sample(all_graphs, k=max(1, len(all_graphs) // 20))

    def pick_graph():
        return rng.choice(hot) if rng.random() < 0.6 else rng.choice(all_graphs)

    mix = [("motif", 0.25), ("exact", 0.20), ("variable", 0.15), ("multi", 0.15),
           ("attribute", 0.08), ("general", 0.07), ("partial", 0.06), ("unsat", 0.04)]
    motifs_w = [m["query_weight"] for m in MOTIFS]
    distinct, kinds = [], {}
    while len(distinct) < n_distinct:
        kind = rng.choices([k for k, _ in mix], weights=[w for _, w in mix])[0]
        if kind == "motif":
            q = motif_query(rng, rng.choices(MOTIFS, weights=motifs_w)[0])
        elif kind == "general":
            q = general_query(rng)
        elif kind == "unsat":
            q = unsatisfiable_query(rng)
        elif kind == "partial":
            q = partial_query(rng, pick_graph(), pick_graph())
        else:
            q = organic_query(rng, pick_graph(), kind)
        if q and q not in kinds:
            kinds[q] = kind
            distinct.append(q)

    # repeats: query popularity follows a Zipf distribution over a random order
    rng.shuffle(distinct)
    weights = [1.0 / (i + 1) ** 0.9 for i in range(len(distinct))]
    log = list(distinct) + rng.choices(distinct, weights=weights, k=n_log - len(distinct))
    rng.shuffle(log)
    return log, kinds

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, help="group number used in file names")
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--scale", type=float, default=1.0, help="multiplies number of graphs")
    ap.add_argument("--distinct-queries", type=int, default=500)
    ap.add_argument("--log-size", type=int, default=1000)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    os.makedirs(args.out, exist_ok=True)
    files, truth = generate_database(rng, args.scale)
    for idx, graphs in files.items():
        with open(os.path.join(args.out, f"Database{args.group}_{idx}.txt"), "w") as f:
            for _, g in graphs:
                f.write(g.to_line() + "\n")
    log, kinds = generate_query_log(rng, files, args.distinct_queries, args.log_size)
    with open(os.path.join(args.out, f"QLog{args.group}.txt"), "w") as f:
        f.write("\n".join(log) + "\n")

    # ground truth for our own experiments
    meta = {
        "seed": args.seed, "scale": args.scale,
        "files": {f"Database{args.group}_{i}.txt": {
            "shape": SHAPES[i][0], "graphs": len(gs),
            "first_global_id": gs[0][0]} for i, gs in files.items()},
        "motifs": {m["name"]: {"data_rate": m["data_rate"], "query_weight": m["query_weight"],
                               "graph_ids": truth[m["name"]]} for m in MOTIFS},
        "query_kinds": kinds,
    }
    with open(os.path.join(args.out, "ground_truth.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"wrote {sum(len(g) for g in files.values())} graphs and {len(log)} queries "
          f"({len(kinds)} distinct) to {args.out}/")


if __name__ == "__main__":
    main()
