"""
visualize.py — Genera:
  1) network_static.png   : imagen estática (matplotlib) coloreada por comunidad,
                             tamaño de nodo según grado, sólo se etiquetan los hubs.
  2) network_interactive.html : red interactiva navegable (pyvis) para explorar
                             a mano en el navegador (zoom, arrastrar, hover).

Uso:
    python visualize.py --top-labels 25 --min-degree 1
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

DATA_DIR = Path("data")

PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
    "#008080", "#e6beff", "#9a6324", "#800000", "#aaffc3",
    "#808000", "#ffd8b1", "#000075", "#808080",
]


def load_graph():
    return nx.read_gexf(DATA_DIR / "graph.gexf")


def static_plot(G, top_labels=25, min_degree=1, out="network_static.png"):
    if min_degree > 0:
        keep = [n for n, d in G.degree() if d >= min_degree]
        G = G.subgraph(keep).copy()

    communities = list(nx.algorithms.community.greedy_modularity_communities(G, weight="weight"))
    node_color = {}
    for i, c in enumerate(communities):
        color = PALETTE[i % len(PALETTE)]
        for n in c:
            node_color[n] = color

    degrees = dict(G.degree())
    sizes = [30 + degrees[n] * 8 for n in G.nodes()]
    colors = [node_color.get(n, "#cccccc") for n in G.nodes()]

    print("Calculando layout (puede tardar un poco en grafos grandes)...")
    pos = nx.spring_layout(G, k=0.35, iterations=50, seed=42, weight="weight")

    plt.figure(figsize=(20, 20))
    nx.draw_networkx_edges(G, pos, alpha=0.15, width=0.6)
    nx.draw_networkx_nodes(G, pos, node_size=sizes, node_color=colors, alpha=0.9, linewidths=0)

    top_nodes = sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)[:top_labels]
    names = nx.get_node_attributes(G, "name")
    labels = {n: names.get(n, n) for n, _ in top_nodes}
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=9, font_weight="bold")

    plt.title("Red de colaboración del rock argentino (rock.com.ar)", fontsize=18)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(DATA_DIR / out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Guardado: {DATA_DIR / out}")


def interactive_plot(G, min_degree=1, out="network_interactive.html"):
    try:
        from pyvis.network import Network
    except ImportError:
        print("Falta pyvis. Instalalo con: pip install pyvis")
        return

    if min_degree > 0:
        keep = [n for n, d in G.degree() if d >= min_degree]
        G = G.subgraph(keep).copy()

    communities = list(nx.algorithms.community.greedy_modularity_communities(G, weight="weight"))
    node_color = {}
    for i, c in enumerate(communities):
        color = PALETTE[i % len(PALETTE)]
        for n in c:
            node_color[n] = color

    net = Network(height="900px", width="100%", bgcolor="#111111", font_color="white",
                   notebook=False)
    net.barnes_hut(gravity=-8000, spring_length=120)

    names = nx.get_node_attributes(G, "name")
    degrees = dict(G.degree())
    for n in G.nodes():
        net.add_node(
            n,
            label=names.get(n, n),
            title=f"{names.get(n, n)} — {degrees[n]} colaboraciones",
            size=8 + degrees[n] * 2,
            color=node_color.get(n, "#888888"),
        )
    for u, v, d in G.edges(data=True):
        net.add_edge(u, v, value=d.get("weight", 1), title=d.get("sources", ""))

    net.set_options("""
    var options = {
      "physics": {"stabilization": {"iterations": 150}}
    }
    """)
    net.write_html(str(DATA_DIR / out), notebook=False)
    print(f"Guardado: {DATA_DIR / out} (abrilo en el navegador)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-labels", type=int, default=25)
    parser.add_argument("--min-degree", type=int, default=1,
                         help="oculta nodos con grado menor a este valor (limpia el dibujo)")
    args = parser.parse_args()

    gexf_path = DATA_DIR / "graph.gexf"
    if not gexf_path.exists():
        print("No existe data/graph.gexf. Corré primero: python analyze.py")
        return
    G = load_graph()
    static_plot(G, top_labels=args.top_labels, min_degree=args.min_degree)
    interactive_plot(G, min_degree=args.min_degree)


if __name__ == "__main__":
    main()
