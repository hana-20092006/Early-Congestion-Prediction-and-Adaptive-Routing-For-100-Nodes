"""
network_setup.py — 100-Node Scale Network
Generates a realistic large-scale network topology with:
  - 100 nodes
  - Random geometric graph for spatial locality (like real ISP topology)
  - Variable edge capacities to model heterogeneous links
"""

import networkx as nx
import random
import numpy as np

RANDOM_SEED = 42
NUM_NODES   = 100


def create_network(seed=RANDOM_SEED, num_nodes=NUM_NODES):
    random.seed(seed)
    np.random.seed(seed)

    # Random geometric graph: nodes connected if within radius → realistic mesh
    # radius=0.15 → ~5-8 avg degree (sparser, more realistic, faster routing)
    G = nx.random_geometric_graph(num_nodes, radius=0.15, seed=seed)

    # Ensure full connectivity — merge isolated components via minimum spanning connections
    components = list(nx.connected_components(G))
    while len(components) > 1:
        # Connect the two closest components by adding one edge
        c1 = list(components[0])
        c2 = list(components[1])
        G.add_edge(random.choice(c1), random.choice(c2))
        components = list(nx.connected_components(G))

    # Re-label nodes from 0-based to 1-based for consistency with original project
    mapping = {n: n + 1 for n in G.nodes()}
    G = nx.relabel_nodes(G, mapping)

    # Assign capacities: core nodes (high degree) get higher capacity
    degrees = dict(G.degree())
    max_deg = max(degrees.values())
    for u, v in G.edges():
        avg_deg = (degrees[u] + degrees[v]) / 2
        # Scale capacity 40–150 based on average degree of the two endpoints
        capacity = int(40 + 110 * (avg_deg / max_deg))
        G[u][v]['capacity'] = capacity

    return G


if __name__ == '__main__':
    G = create_network()
    print(f"Nodes   : {G.number_of_nodes()}")
    print(f"Edges   : {G.number_of_edges()}")
    print(f"Avg degree: {sum(d for _, d in G.degree()) / G.number_of_nodes():.2f}")
    print(f"Diameter  : {nx.diameter(G)}")
    print("Network created successfully!")