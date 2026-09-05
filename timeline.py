"""
timeline.py — Timeline interactivo: eje X = año de debut de cada artista
(su disco más antiguo con año detectado), eje Y = grado (cantidad de
colaboraciones). Permite ver si los grandes hubs surgieron todos en una
época dorada particular, o si están distribuidos parejo a través de las
décadas. Coloreado por comunidad, tamaño de punto = grado.

Requiere haber corrido antes:
    python scraper.py discs   (con la versión que extrae 'year')
    python analyze.py

Uso:
    python timeline.py
    python timeline.py --min-degree 2   # oculta artistas muy periféricos
"""
import argparse
import csv
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go

from common import load_json

DATA_DIR = Path("data")


def compute_first_year(artists: dict, disc_credits: dict):
    """Para cada artista, su año de debut = año del disco más antiguo
    (con año detectado) en su propia discografía."""
    first_year = {}
    for slug, info in artists.items():
        years = []
        for d in info.get("discography", []):
            credit = disc_credits.get(d["url"])
            if credit and credit.get("year"):
                years.append(credit["year"])
        if years:
            first_year[slug] = min(years)
    return first_year


def load_nodes_table():
    rows = {}
    with open(DATA_DIR / "nodes.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["slug"]] = row
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-degree", type=int, default=1,
                         help="oculta artistas con grado menor a este valor")
    parser.add_argument("--top-communities", type=int, default=10,
                         help="cuántas comunidades mostrar con color propio; el resto se agrupa en 'Otras'")
    args = parser.parse_args()

    nodes_path = DATA_DIR / "nodes.csv"
    if not nodes_path.exists():
        print("No existe data/nodes.csv. Corré primero: python analyze.py")
        return

    artists = load_json(DATA_DIR / "artists.json", {})
    disc_credits = load_json(DATA_DIR / "disc_credits.json", {})
    nodes = load_nodes_table()

    first_year = compute_first_year(artists, disc_credits)

    xs, ys, names, communities, degrees = [], [], [], [], []
    for slug, year in first_year.items():
        row = nodes.get(slug)
        if not row:
            continue
        degree = int(row["degree"])
        if degree < args.min_degree:
            continue
        xs.append(year)
        ys.append(degree)
        names.append(row["name"])
        communities.append(row["community"])
        degrees.append(degree)

    # agrupar comunidades chicas en "Otras" para que la leyenda de colores
    # sea legible (si no, con decenas de comunidades los tonos se confunden)
    from collections import Counter
    comm_counts = Counter(communities)
    top_comms = {c for c, _ in comm_counts.most_common(args.top_communities)}

    # nombrar cada comunidad con su artista de mayor grado (en vez de un
    # número suelto), igual que en heatmap.py, para que la leyenda sea legible
    comm_top_artist = {}
    for c in top_comms:
        members = [(n, d) for n, cc, d in zip(names, communities, degrees) if cc == c]
        comm_top_artist[c] = max(members, key=lambda t: t[1])[0]

    def label_for(c):
        return f"{comm_top_artist[c]} y otros" if c in top_comms else "Otras (comunidades chicas)"

    display_communities = [label_for(c) for c in communities]

    if not xs:
        print("No hay suficientes datos (¿corriste scraper.py discs con la "
              "versión que extrae 'year', y después analyze.py?)")
        return

    fig = px.scatter(
        x=xs, y=ys,
        color=display_communities,
        size=degrees,
        size_max=40,
        hover_name=names,
        labels={"x": "Año de debut (disco más antiguo detectado)",
                "y": "Grado (cantidad de colaboraciones)",
                "color": "Comunidad"},
        title="Rock argentino: año de debut vs. conexiones en la red de colaboración",
        opacity=0.75,
    )
    fig.update_layout(
        template="plotly_dark",
        legend_title_text="Comunidad",
        height=750,
    )
    fig.update_traces(marker=dict(line=dict(width=0.5, color="white")))

    out_path = DATA_DIR / "timeline_interactive.html"
    fig.write_html(str(out_path), include_plotlyjs="inline")
    print(f"Guardado: {out_path} (abrilo en el navegador)")
    print(f"Artistas graficados: {len(xs)}")


if __name__ == "__main__":
    main()
