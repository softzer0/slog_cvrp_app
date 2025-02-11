import numpy as np

from ..common import get_unassigned_addresses

def get_depot_and_genes(nodes):
    depot = (len(nodes) - 1, 0)
    genes = [(i, int(nodes[i][1])) for i in range(len(nodes) - 1)]
    return depot, genes

def prepare_w_matrix(user_id, depot_addr_id):
    addresses = get_unassigned_addresses(user_id).all()
    if len(addresses) < 3:
        raise Exception("Not enough available addresses")
    coords = []
    nodes = []
    depot_coords = None
    depot_node = None
    for address in addresses:
        c = address.coords.split(',')
        coords_ = (float(c[0]), float(c[1]))
        if address.id != depot_addr_id:
            coords.append(coords_)
            nodes.append((address.id, address.capacity, address.address))
        else:
            depot_coords = coords_
            depot_node = (address.id, address.address)
    if not depot_node:
        raise Exception("Depot not found among unassigned addresses")
    nodes.append(depot_node)
    coords = np.concatenate((coords, [depot_coords]))
    matrix = np.empty((len(nodes), len(nodes)))
    for i in range(len(nodes)):
        for j in range(i, len(nodes)):
            matrix[i][j] = np.linalg.norm(coords[i] - coords[j])
            matrix[j][i] = matrix[i][j]
    return coords, matrix, nodes
