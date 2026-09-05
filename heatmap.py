"""
heatmap.py — Mapa de calor: décadas (eje X) vs comunidades (eje Y),
donde el color indica cuántos discos de esa comunidad salieron en esa
década. Muestra qué comunidades (escenas/géneros) dominaron cada época.

Requiere haber corrido antes:
    python scraper.py discs   (con la versión que extrae 'year')
    python analyze.py

Uso:
    python heatmap.py
    python heatmap.py --top-communities 10
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common import load_json

DATA_DIR = Path("data")


def load_nodes_table():
    rows = {}
    with open(DATA_DIR / "nodes.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["slug"]] = row
    return rows


def community_label(comm_id: int, nodes: dict):
    """Nombra la comunidad con su artista de mayor grado, para que el
    heatmap sea legible (en vez de mostrar solo un número de comunidad)."""
    members = [r for r in nodes.values() if r["community"] == str(comm_id)]
    if not members:
        return f"Comunidad {comm_id}"
    top = max(members, key=lambda r: int(r["degree"]))
    return f"#{comm_id}: {top['name']} (+{len(members)-1})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-communities", type=int, default=12,
                         help="cuántas comunidades mostrar (las más grandes)")
    args = parser.parse_args()

    nodes_path = DATA_DIR / "nodes.csv"
    if not nodes_path.exists():
        print("No existe data/nodes.csv. Corré primero: python analyze.py")
        return

    artists = load_json(DATA_DIR / "artists.json", {})
    disc_credits = load_json(DATA_DIR / "disc_credits.json", {})
    nodes = load_nodes_table()

    # contar tamaño de cada comunidad para elegir las N más grandes
    comm_sizes = defaultdict(int)
    for r in nodes.values():
        comm_sizes[r["community"]] += 1
    top_comms = sorted(comm_sizes, key=lambda c: comm_sizes[c], reverse=True)
    top_comms = [c for c in top_comms if c != "-1"][:args.top_communities]

    # matriz comunidad x década, contando discos (evitando duplicar el
    # mismo disco varias veces si tiene más de un artista de la misma
    # comunidad acreditado)
    counts = defaultdict(lambda: defaultdict(int))
    for slug, info in artists.items():
        row = nodes.get(slug)
        if not row or row["community"] not in top_comms:
            continue
        comm = row["community"]
        seen_discs_this_artist = set()
        for d in info.get("discography", []):
            credit = disc_credits.get(d["url"])
            if not credit or not credit.get("year"):
                continue
            if d["url"] in seen_discs_this_artist:
                continue
            seen_discs_this_artist.add(d["url"])
            decade = (credit["year"] // 10) * 10
            counts[comm][decade] += 1

    if not counts:
        print("No hay suficientes datos (¿corriste scraper.py discs con la "
              "versión que extrae 'year', y después analyze.py?)")
        return

    all_decades = sorted({dec for c in counts.values() for dec in c})
    matrix = np.zeros((len(top_comms), len(all_decades)))
    for i, comm in enumerate(top_comms):
        for j, dec in enumerate(all_decades):
            matrix[i, j] = counts[comm].get(dec, 0)

    labels = [community_label(int(c), nodes) for c in top_comms]

    plt.figure(figsize=(max(10, len(all_decades) * 1.2), max(6, len(top_comms) * 0.6)))
    im = plt.imshow(matrix, aspect="auto", cmap="YlOrRd")
    plt.colorbar(im, label="Cantidad de discos")
    plt.xticks(range(len(all_decades)), [f"{d}s" for d in all_decades], rotation=45)
    plt.yticks(range(len(top_comms)), labels)
    plt.title("Actividad discográfica por comunidad y década")

    # anotar valores dentro de cada celda
    for i in range(len(top_comms)):
        for j in range(len(all_decades)):
            val = int(matrix[i, j])
            if val > 0:
                color = "white" if val > matrix.max() * 0.5 else "black"
                plt.text(j, i, str(val), ha="center", va="center",
                          color=color, fontsize=8)

    plt.tight_layout()
    out_path = DATA_DIR / "heatmap_comunidad_decada.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Guardado: {out_path}")


if __name__ == "__main__":
    main()
