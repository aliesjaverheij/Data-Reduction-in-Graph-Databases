""" Builds the D1 deliverable data19.zip: generate data, compute statistics, write README.

python data_generation/build_d1.py --group 19

"""
import argparse
import glob
import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_dataset import _evaluate, _init


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    G, out = args.group, args.out

    subprocess.run([sys.executable, os.path.join(HERE, "generate_dataset.py"),
                    "--group", G, "--out", out, "--seed", str(args.seed)], check=True)
    dbs = sorted(glob.glob(os.path.join(out, f"Database{G}_*.txt")))
    qlog = os.path.join(out, f"QLog{G}.txt")
    lines = [l.strip() for l in open(qlog) if l.strip()]
    freq = Counter(lines)

    with Pool(initializer=_init, initargs=(dbs,)) as pool:
        results = pool.map(_evaluate, list(freq), chunksize=4)
    fulls = [f for _, f, _ in results]
    hist = Counter("0" if f == 0 else "1" if f == 1 else "2-10" if f <= 10 else
                   "11-100" if f <= 100 else "101-1000" if f <= 1000 else ">1000"
                   for f in fulls)
    hist_txt = ", ".join(f"{hist[k]} queries with {k} answers"
                         for k in ["0", "1", "2-10", "11-100", "101-1000", ">1000"])

    meta = json.load(open(os.path.join(out, "ground_truth.json")))
    counts = {int(k.split("_")[1].split(".")[0]): v["graphs"] for k, v in meta["files"].items()}
    fill = {f"N{i}": counts[i] for i in counts}
    fill.update(G=G, NT=sum(counts.values()), Q=len(lines), QD=len(freq),
                TOP=freq.most_common(1)[0][1], ONCE=sum(1 for c in freq.values() if c == 1),
                MAXA=max(fulls), HIST=hist_txt, SEED=args.seed)
    readme = open(os.path.join(HERE, "README_template.txt")).read().format(**fill)
    with open(os.path.join(out, "README.txt"), "w") as f:
        f.write(readme)

    zpath = os.path.join(out, f"data{G}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in dbs + [qlog, os.path.join(out, "README.txt")]:
            z.write(p, arcname=os.path.basename(p))
    print(f"built {zpath} ({os.path.getsize(zpath) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
