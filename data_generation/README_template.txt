Group {G} - Data Reduction in Graph Databases - D1 dataset and query log
=======================================================================

FILES
-----
Database{G}_1.txt  "small"  : {N1} small random social graphs (3-10 nodes, avg. degree ~2.5)
Database{G}_2.txt  "large"  : {N2} large graphs (100-400 nodes) built with preferential
                              attachment, so they contain hubs like real social networks
Database{G}_3.txt  "star"   : {N3} star-shaped graphs (one centre, 4-59 leaves)
Database{G}_4.txt  "line"   : {N4} line/chain-shaped graphs (4-40 nodes)
Database{G}_5.txt  "cycle"  : {N5} cycles (3-30 nodes), some with 1-2 extra chords
Database{G}_6.txt  "tree"   : {N6} trees (5-80 nodes, branching factor 2-4)
QLog{G}.txt                 : {Q} queries ({QD} distinct), one query per line

The union of the six database files is the database D (one graph per line, node counts above exclude planted motifs,
{NT} graphs in total). The files can also be used separately to test how a method
behaves on one graph shape or size.

FORMAT
------
Exactly as in the assignment. A graph is one line of comma-separated triples:
  <17,knows,23>        edge from node 17 to node 23 with label knows
  <17,city,"Utrecht">  attribute city:"Utrecht" of node 17
A query is one line of comma-separated paths; path components are separated by dots:
  9001.married.X.worksAt.Y.name."Adyen",X.city.A
- Node ids are positive integers; edge labels and attribute names start with a
  lowercase letter and contain only letters/digits.
- Variables start with an uppercase letter (X, Y, Z, W, V, U, A). A variable that
  appears in several paths of the same query must be bound to the same node/value
  (conjunctive semantics). A variable as last component after an attribute name
  (e.g. X.city.A) binds to the attribute value.
- A path may end with an edge label/attribute name (e.g. X.friendOf.Y.follows),
  meaning the last node has an outgoing edge or attribute with that name.
- Attribute values never contain commas, dots, quotes or spaces, so files can be
  split safely on "," and ".". Numbers in attributes are quoted strings (age:"34").

DOMAIN
------
A social network with four node kinds (attribute type): person, company, city,
university. Edge labels depend on the kinds of the endpoints (knows, friendOf,
follows, colleagueOf, married, parentOf, siblingOf, mentors, blocked, worksAt,
manages, founded, investsIn, livesIn, bornIn, visited, studiesAt, graduatedFrom,
teachesAt, partnerOf, competitorOf, acquired, locatedIn, employs, sponsors,
connectedTo, twinnedWith, hasResident, mayor, hosts). Attributes: name, age,
city, job, gender (persons), name, sector, founded (companies; real Dutch companies
with their actual sector and founding year), name, country,
population (cities), name, ranking (universities).
Label and attribute-value frequencies follow a Zipf distribution: a few labels and
values (knows, Amsterdam, engineer, ...) are very common, most are rare.

Node ids are drawn per graph from a shared id range (1-60 for small graphs, 1-500
for star/line/cycle/tree, 1-2000 for large graphs). The same id therefore occurs
in many graphs, and queries with constant node ids can match several graphs.

PLANTED PATTERNS (known ground truth)
-------------------------------------
Six small sub-graphs ("motifs") with fixed ids in the range 9001-9054 are planted
into a known fraction of the graphs and attached to one of their nodes. They differ
in how often they occur in the data and how often they are queried, e.g.
  rare in data + frequently queried   (9001.married.9002.worksAt.9003.locatedIn.9004)
  common in data + frequently queried (9011.knows.9012.knows.9013)
  common in data + never queried      (9031.follows.9032)
A good reduction method should keep graphs that contain rare but frequently
queried patterns, and should not waste budget on common/unqueried ones.

QUERY LOG
---------
{QD} distinct queries, repeated according to a Zipf popularity distribution to
{Q} lines (the most popular query occurs {TOP} times, {ONCE} queries occur once).
The repeats are on purpose: the frequency of a query should count as its weight.
Query kinds:
- motif queries over the planted patterns (constant ids, partly generalised
  with variables)
- exact paths (constant ids) sampled by random walks from graphs; 60% of these
  come from a "hot" 5% of the graphs, so the workload is skewed
- the same paths with node ids replaced by variables
- multi-path queries (2-4 paths from one start node, sharing variables)
- attribute queries (e.g. X.livesIn.Y.name."Utrecht", X.job."nurse")
- very general queries that match most graphs (e.g. X.knows.Y)
- queries combining paths from two different graphs, so most graphs satisfy them
  only partially
- unsatisfiable queries (unknown labels or values) that no graph satisfies
Answer sizes (number of graphs fully satisfying a distinct query) range from 0
to {MAXA}: {HIST}.

The data was generated with a seeded Python generator and can be regenerated
or scaled up by changing its parameters (seed {SEED}).
