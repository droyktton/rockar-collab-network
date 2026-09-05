"""
ego_network.py — Visualiza el "ego-network" de un artista: él mismo, sus
colaboradores directos, y (opcionalmente) los colaboradores de sus
colaboradores. Mucho más legible que ver los 5778 nodos juntos, e ideal
para contar la historia de un artista puntual.

Uso:
    python ego_network.py "Charly Garcia"
    python ego_network.py "Charly Garcia" --hops 2
    python ego_network.py "Charly Garcia" --hops 1 --min-degree 2
"""
import argparse
import unicodedata
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
]


def normalize(s: str) -> str:
    s = s.strip().lower()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def find_node(G: nx.Graph, query: str) -> str:
    """Busca un nodo por nombre (o slug), tolerando acentos/mayúsculas."""
    q = normalize(query)
    names = nx.get_node_attributes(G, "name")

    # match exacto por nombre normalizado
    for node, name in names.items():
        if normalize(name) == q:
            return node
    # match exacto por slug
    for node in G.nodes():
        if normalize(node) == q.replace(" ", "-"):
            return node
    # match parcial (contiene la query)
    candidates = [node for node, name in names.items() if q in normalize(name)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"Varios artistas coinciden con '{query}':")
        for c in candidates[:15]:
            print(f"  - {names.get(c, c)}")
        raise SystemExit("Sé más específico, o usá el nombre completo entre comillas.")
    raise SystemExit(f"No se encontró ningún artista que coincida con '{query}'.")


def build_ego_graph(G: nx.Graph, center: str, hops: int, min_degree: int = 0):
    ego = nx.ego_graph(G, center, radius=hops)
    if min_degree > 0:
        # nunca sacar al centro, aunque tenga poco grado dentro del ego-graph
        keep = {n for n, d in ego.degree() if d >= min_degree} | {center}
        ego = ego.subgraph(keep).copy()
    return ego


def static_plot(ego: nx.Graph, center: str, out: str):
    names = nx.get_node_attributes(ego, "name")
    degrees_full = dict(ego.degree())

    communities = list(nx.algorithms.community.greedy_modularity_communities(ego, weight="weight"))
    node_color = {}
    for i, c in enumerate(communities):
        color = PALETTE[i % len(PALETTE)]
        for n in c:
            node_color[n] = color
    node_color[center] = "#ffffff"  # el centro siempre se destaca en blanco

    sizes = [900 if n == center else 200 + degrees_full[n] * 30 for n in ego.nodes()]
    colors = [node_color.get(n, "#cccccc") for n in ego.nodes()]
    edge_colors = ["#ff5555" if center in e else "#cccccc" for e in ego.edges()]
    edge_widths = [2.2 if center in e else 0.8 for e in ego.edges()]

    pos = nx.spring_layout(ego, k=0.6, iterations=100, seed=42, weight="weight")

    plt.figure(figsize=(14, 14))
    nx.draw_networkx_edges(ego, pos, edge_color=edge_colors, width=edge_widths, alpha=0.6)
    nx.draw_networkx_nodes(ego, pos, node_size=sizes, node_color=colors,
                            edgecolors="#333333", linewidths=1.2)
    labels = {n: names.get(n, n) for n in ego.nodes()}
    nx.draw_networkx_labels(ego, pos, labels=labels, font_size=9,
                             font_weight="bold")

    plt.title(f"Red de colaboración de {names.get(center, center)}", fontsize=18)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(DATA_DIR / out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Guardado: {DATA_DIR / out}")


def interactive_plot(ego: nx.Graph, center: str, out: str):
    try:
        from pyvis.network import Network
    except ImportError:
        print("Falta pyvis. Instalalo con: pip install pyvis")
        return

    names = nx.get_node_attributes(ego, "name")
    degrees = dict(ego.degree())

    communities = list(nx.algorithms.community.greedy_modularity_communities(ego, weight="weight"))
    node_color = {}
    for i, c in enumerate(communities):
        color = PALETTE[i % len(PALETTE)]
        for n in c:
            node_color[n] = color

    net = Network(height="800px", width="100%", bgcolor="#111111", font_color="white",
                   notebook=False, cdn_resources="in_line")

    for n in ego.nodes():
        is_center = n == center
        net.add_node(
            n,
            label=names.get(n, n),
            title=f"{names.get(n, n)} — {degrees[n]} colaboraciones",
            size=40 if is_center else 12 + degrees[n] * 3,
            color="#ffffff" if is_center else node_color.get(n, "#888888"),
            borderWidth=3 if is_center else 1,
        )
    for u, v, d in ego.edges(data=True):
        is_center_edge = center in (u, v)
        net.add_edge(u, v, value=d.get("weight", 1), title=d.get("sources", ""),
                     color="#ff5555" if is_center_edge else "#666666")

    net.set_options("""
    var options = {
      "physics": {"stabilization": {"iterations": 150, "fit": true}, "solver": "barnesHut"}
    }
    """)
    net.write_html(str(DATA_DIR / out), notebook=False)

    html_path = DATA_DIR / out
    html = html_path.read_text(encoding="utf-8")
    disable_physics_js = """
    <script type="text/javascript">
      network.once("stabilizationIterationsDone", function () {
        network.setOptions({ physics: false });
      });
    </script>
    """
    html = html.replace("</body>", disable_physics_js + "</body>")
    html_path.write_text(html, encoding="utf-8")
    print(f"Guardado: {DATA_DIR / out} (abrilo en el navegador)")


def print_summary(ego: nx.Graph, center: str):
    names = nx.get_node_attributes(ego, "name")
    print(f"\n=== Ego-network de {names.get(center, center)} ===")
    print(f"Nodos: {ego.number_of_nodes()} | Aristas: {ego.number_of_edges()}")
    direct = sorted(ego.neighbors(center), key=lambda n: ego.degree(n), reverse=True)
    print(f"\nColaboradores directos ({len(direct)}):")
    for n in direct[:30]:
        print(f"  - {names.get(n, n)} (grado {ego.degree(n)})")
    if len(direct) > 30:
        print(f"  ... y {len(direct) - 30} más")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artist", help="Nombre del artista (o parte del nombre)")
    parser.add_argument("--hops", type=int, default=1,
                         help="1 = solo colaboradores directos, 2 = también colaboradores de colaboradores")
    parser.add_argument("--min-degree", type=int, default=0,
                         help="oculta nodos periféricos con grado menor a este valor (dentro del ego-graph)")
    args = parser.parse_args()

    gexf_path = DATA_DIR / "graph.gexf"
    if not gexf_path.exists():
        print("No existe data/graph.gexf. Corré primero: python analyze.py")
        return

    G = nx.read_gexf(gexf_path)
    center = find_node(G, args.artist)
    ego = build_ego_graph(G, center, args.hops, args.min_degree)

    print_summary(ego, center)

    slug_safe = center.replace("/", "-")
    static_plot(ego, center, f"ego_{slug_safe}.png")
    interactive_plot(ego, center, f"ego_{slug_safe}.html")


if __name__ == "__main__":
    main()
