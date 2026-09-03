"""
analyze.py — Construye el grafo de colaboración a partir de los datos
descargados y calcula sus propiedades estructurales.

Uso:
    python analyze.py

Salidas (en ./data):
    graph.gexf / graph.graphml   -> para abrir en Gephi si querés explorar a mano
    nodes.csv, edges.csv          -> tablas planas
    report.md                     -> resumen legible de las métricas
"""
import csv
import itertools
from pathlib import Path

import networkx as nx

from common import load_json

DATA_DIR = Path("data")


def build_graph(min_disc_shared=1):
    artists = load_json(DATA_DIR / "artists.json", {})
    disc_credits = load_json(DATA_DIR / "disc_credits.json", {})

    G = nx.Graph()

    # nodos
    for slug, info in artists.items():
        G.add_node(slug, name=info.get("name", slug))

    # aristas por menciones cruzadas en biografías (bio_links)
    for slug, info in artists.items():
        for other in info.get("bio_links", []):
            if other == slug:
                continue
            if other not in G:
                # el otro artista puede no tener ficha propia descargada;
                # lo agregamos igual como nodo "externo" mínimo
                G.add_node(other, name=other.replace("-", " ").title())
            if G.has_edge(slug, other):
                G[slug][other]["weight"] += 1
                G[slug][other]["sources"].add("bio")
            else:
                G.add_edge(slug, other, weight=1, sources={"bio"})

    # aristas por co-autoría de disco (todos contra todos en resolved_slugs)
    for disc in disc_credits.values():
        slugs = [s for s in disc.get("resolved_slugs", []) if s]
        for a, b in itertools.combinations(sorted(set(slugs)), 2):
            for n in (a, b):
                if n not in G:
                    G.add_node(n, name=n.replace("-", " ").title())
            if G.has_edge(a, b):
                G[a][b]["weight"] += 1
                G[a][b]["sources"].add("disco")
            else:
                G.add_edge(a, b, weight=1, sources={"disco"})

    # sources como set no serializa bien -> pasar a string para exportar
    for u, v, d in G.edges(data=True):
        d["sources"] = ",".join(sorted(d.get("sources", [])))

    return G


def compute_metrics(G: nx.Graph):
    metrics = {}
    metrics["n_nodes"] = G.number_of_nodes()
    metrics["n_edges"] = G.number_of_edges()
    metrics["density"] = nx.density(G)
    metrics["avg_degree"] = sum(dict(G.degree()).values()) / max(G.number_of_nodes(), 1)

    components = sorted(nx.connected_components(G), key=len, reverse=True)
    metrics["n_components"] = len(components)
    metrics["largest_component_size"] = len(components[0]) if components else 0

    G_main = G.subgraph(components[0]).copy() if components else G.copy()
    metrics["avg_clustering"] = nx.average_clustering(G)

    # diámetro / camino promedio sólo sobre la componente principal
    # (si es muy grande, esto puede tardar; se puede comentar si hace falta)
    try:
        if G_main.number_of_nodes() <= 3000:
            metrics["diameter_main_component"] = nx.diameter(G_main)
            metrics["avg_shortest_path_main_component"] = nx.average_shortest_path_length(G_main)
        else:
            metrics["diameter_main_component"] = "omitido (grafo grande, ver README)"
            metrics["avg_shortest_path_main_component"] = "omitido (grafo grande, ver README)"
    except nx.NetworkXError:
        metrics["diameter_main_component"] = "N/A"
        metrics["avg_shortest_path_main_component"] = "N/A"

    # centralidades / hubs
    degree_c = nx.degree_centrality(G)
    betweenness_c = nx.betweenness_centrality(G_main, k=min(500, G_main.number_of_nodes()), seed=42)
    eigen_c = {}
    try:
        eigen_c = nx.eigenvector_centrality(G, max_iter=1000)
    except nx.PowerIterationFailedConvergence:
        eigen_c = {n: 0 for n in G.nodes()}
    pagerank = nx.pagerank(G)

    names = nx.get_node_attributes(G, "name")

    def top(d, n=20):
        return sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]

    metrics["top_degree"] = [(names.get(s, s), G.degree(s), v) for s, v in top(degree_c)]
    metrics["top_betweenness"] = [(names.get(s, s), v) for s, v in top(betweenness_c)]
    metrics["top_eigenvector"] = [(names.get(s, s), v) for s, v in top(eigen_c)]
    metrics["top_pagerank"] = [(names.get(s, s), v) for s, v in top(pagerank)]

    # comunidades (detección simple por modularidad)
    communities = list(nx.algorithms.community.greedy_modularity_communities(G, weight="weight"))
    metrics["n_communities"] = len(communities)
    metrics["communities_top5_by_size"] = [
        (len(c), [names.get(s, s) for s in list(c)[:8]]) for c in sorted(communities, key=len, reverse=True)[:5]
    ]

    return metrics, communities, degree_c, betweenness_c, eigen_c, pagerank


def export_tables(G, degree_c, betweenness_c, eigen_c, pagerank, communities):
    names = nx.get_node_attributes(G, "name")
    node_to_comm = {}
    for i, c in enumerate(communities):
        for n in c:
            node_to_comm[n] = i

    with open(DATA_DIR / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slug", "name", "degree", "degree_centrality", "betweenness",
                    "eigenvector", "pagerank", "community"])
        for n in G.nodes():
            w.writerow([
                n, names.get(n, n), G.degree(n),
                round(degree_c.get(n, 0), 5),
                round(betweenness_c.get(n, 0), 5),
                round(eigen_c.get(n, 0), 5),
                round(pagerank.get(n, 0), 5),
                node_to_comm.get(n, -1),
            ])

    with open(DATA_DIR / "edges.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "target", "weight", "sources"])
        for u, v, d in G.edges(data=True):
            w.writerow([u, v, d.get("weight", 1), d.get("sources", "")])


def write_report(metrics, path=DATA_DIR / "report.md"):
    lines = []
    lines.append("# Red de colaboración del rock argentino — rock.com.ar\n")
    lines.append("## Propiedades generales\n")
    lines.append(f"- Nodos (artistas): **{metrics['n_nodes']}**")
    lines.append(f"- Aristas (colaboraciones): **{metrics['n_edges']}**")
    lines.append(f"- Densidad: {metrics['density']:.5f}")
    lines.append(f"- Grado promedio: {metrics['avg_degree']:.2f}")
    lines.append(f"- Componentes conexas: {metrics['n_components']}")
    lines.append(f"- Tamaño de la componente principal: {metrics['largest_component_size']}")
    lines.append(f"- Coeficiente de clustering promedio: {metrics['avg_clustering']:.4f}")
    lines.append(f"- Diámetro (componente principal): {metrics['diameter_main_component']}")
    lines.append(f"- Camino más corto promedio (componente principal): {metrics['avg_shortest_path_main_component']}")
    lines.append(f"- Comunidades detectadas: {metrics['n_communities']}\n")

    lines.append("## Hubs por grado (más colaboradores directos)\n")
    for name, deg, _ in metrics["top_degree"]:
        lines.append(f"- {name}: {deg} colaboraciones")

    lines.append("\n## Hubs por intermediación (betweenness) — conectan escenas distintas\n")
    for name, v in metrics["top_betweenness"]:
        lines.append(f"- {name}: {v:.4f}")

    lines.append("\n## Hubs por PageRank\n")
    for name, v in metrics["top_pagerank"]:
        lines.append(f"- {name}: {v:.5f}")

    lines.append("\n## Comunidades más grandes (muestra de integrantes)\n")
    for size, sample in metrics["communities_top5_by_size"]:
        lines.append(f"- Tamaño {size}: {', '.join(sample)}...")

    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main():
    G = build_graph()
    if G.number_of_nodes() == 0:
        print("El grafo está vacío. ¿Corriste scraper.py primero?")
        return
    nx.write_gexf(G, DATA_DIR / "graph.gexf")
    nx.write_graphml(G, DATA_DIR / "graph.graphml")

    metrics, communities, degree_c, betweenness_c, eigen_c, pagerank = compute_metrics(G)
    export_tables(G, degree_c, betweenness_c, eigen_c, pagerank, communities)
    write_report(metrics)
    print(f"\nArchivos generados en {DATA_DIR.resolve()}: graph.gexf, graph.graphml, "
          f"nodes.csv, edges.csv, report.md")


if __name__ == "__main__":
    main()
