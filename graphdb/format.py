""" Parsing, serialisation and (reference) query matching for the course graph format.

Graph line:  <1,top,2>,<2,right,3>,<1,isBoss,"yes">
Query line:  5.married.X.city."Utrecht",X.worksAt.Y

Path components: node ids (digits), variables (start with an uppercase letter),
edge labels / attribute names (start with a lowercase letter) and quoted strings.
Variables are scoped per query, i.e. a variable occurring in two paths of the same
query must be bound to the same value in both.

"""
import re
from collections import defaultdict

TRIPLE_RE = re.compile(r'<(\d+),([A-Za-z0-9]+),("[^",.<>]*"|\d+)>')
LABEL_RE = re.compile(r'^[a-z][A-Za-z0-9]*$')
VAR_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')
STRING_RE = re.compile(r'^"[^",.<>]*"$')


class Graph:
    __slots__ = ("nodes", "out", "attrs", "labels")

    def __init__(self):
        self.nodes = set()
        self.out = defaultdict(list)     # node -> [(label, dst)]
        self.attrs = defaultdict(list)   # node -> [(name, value)]
        self.labels = set()              # all edge labels and attribute names

    def add_edge(self, s, l, d):
        self.nodes.update((s, d))
        self.out[s].append((l, d))
        self.labels.add(l)

    def add_attr(self, n, name, value):
        self.nodes.add(n)
        self.attrs[n].append((name, value))
        self.labels.add(name)

    def to_line(self):
        parts = []
        for s in sorted(self.out):
            parts += [f"<{s},{l},{d}>" for l, d in self.out[s]]
        for n in sorted(self.attrs):
            parts += [f'<{n},{a},"{v}">' for a, v in self.attrs[n]]
        return ",".join(parts)


def parse_graph(line):
    line = line.strip()
    g = Graph()
    pos = 0
    for m in TRIPLE_RE.finditer(line):
        between = line[pos:m.start()]
        if between not in ("", ","):
            raise ValueError(f"unexpected text {between!r} in graph line")
        pos = m.end()
        s, l, third = int(m.group(1)), m.group(2), m.group(3)
        if third.startswith('"'):
            g.add_attr(s, l, third[1:-1])
        else:
            g.add_edge(s, l, int(third))
    if line[pos:] != "":
        raise ValueError(f"trailing text {line[pos:]!r} in graph line")
    return g


# queries
def _term(tok):
    if tok.isdigit():
        return ("node", int(tok))
    if VAR_RE.match(tok):
        return ("var", tok)
    if STRING_RE.match(tok):
        return ("str", tok[1:-1])
    if LABEL_RE.match(tok):
        return ("label", tok)
    raise ValueError(f"invalid path component {tok!r}")


def parse_path(text):
    comps = [_term(t) for t in text.strip().split(".")]

    # validity rules from the assignment
    if comps[0][0] not in ("node", "var"):
        raise ValueError(f"path must start with a node: {text}")
    for i, (kind, _) in enumerate(comps):
        expect_label = i % 2 == 1
        if expect_label and kind != "label":
            raise ValueError(f"component {i} must be a label: {text}")
        if not expect_label and i > 0:
            if kind == "label":
                raise ValueError(f"component {i} must be node/var/string: {text}")
            if kind == "str" and i != len(comps) - 1:
                raise ValueError(f"string must be the last component: {text}")
    return comps


def parse_query(line):
    return [parse_path(p) for p in line.strip().split(",") if p.strip()]


def path_labels(path):
    return {v for k, v in path if k == "label"}


def _match_path(g, path, binding):
    kind, val = path[0]
    if kind == "node":
        starts = [val] if val in g.nodes else []
        yield from _walk(g, path, 1, val, binding) if starts else ()
        return
    if val in binding:
        b = binding[val]
        if isinstance(b, int) and b in g.nodes:
            yield from _walk(g, path, 1, b, binding)
        return
    for n in g.nodes:
        yield from _walk(g, path, 1, n, {**binding, val: n})


def _walk(g, path, i, node, binding):
    if i == len(path):
        yield binding
        return
    label = path[i][1]
    last = i + 1 == len(path)
    if last:  # path ends with a label
        if any(l == label for l, _ in g.out.get(node, ())) or \
           any(a == label for a, _ in g.attrs.get(node, ())):
            yield binding
        return
    kind, val = path[i + 1]
    final = i + 2 == len(path)
    if kind == "str":
        if any(a == label and v == val for a, v in g.attrs.get(node, ())):
            yield binding
        return
    for l, d in g.out.get(node, ()):
        if l != label:
            continue
        if kind == "node":
            if d == val:
                yield from _walk(g, path, i + 2, d, binding)
        elif val in binding:
            if binding[val] == d:
                yield from _walk(g, path, i + 2, d, binding)
        else:
            yield from _walk(g, path, i + 2, d, {**binding, val: d})
    if kind == "var" and final:
        for a, v in g.attrs.get(node, ()):
            if a == label and (val not in binding or binding[val] == v):
                yield {**binding, val: v}


def satisfies_path(g, path):
    if not path_labels(path) <= g.labels:
        return False
    return next(_match_path(g, path, {}), None) is not None


def satisfies_query(g, query):
    """ True iff one variable binding satisfies all paths of the query."""
    if not set().union(*map(path_labels, query)) <= g.labels:
        return False

    def rec(i, binding):
        if i == len(query):
            return True
        return any(rec(i + 1, b) for b in _match_path(g, query[i], binding))
    return rec(0, {})


def path_to_str(path):
    return ".".join(f'"{v}"' if k == "str" else str(v) for k, v in path)
