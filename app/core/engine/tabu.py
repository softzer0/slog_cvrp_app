from random import shuffle

class Tabu:
    def __init__(self, matrix, depot):
        self.matrix = matrix
        self.depot = depot

    def execute(self, route, max_iterations):
        best_solution = list(range(len(route)))
        best_cost = self.compute_cost(route, best_solution)
        tabu_list = []

        for _ in range(max_iterations):
            # Generate a list of all possible moves
            moves = []
            for j in range(len(route)):
                for k in range(len(route)):
                    if j != k:
                        moves.append((j, k))

            # Shuffle the list of moves to introduce randomness
            shuffle(moves)

            # Iterate over the list of moves and select the first valid one
            found_move = False
            for j, k in moves:
                if (j, k) not in tabu_list and (k, j) not in tabu_list:
                    # Make the move
                    solution = best_solution[:]
                    solution[j], solution[k] = solution[k], solution[j]
                    cost = self.compute_cost(route, solution)

                    # Check if the move is an improvement
                    if cost < best_cost:
                        best_solution = solution
                        best_cost = cost
                        found_move = True
                        break

            # If no valid moves were found, reset the tabu list
            if not found_move:
                tabu_list = []

            tabu_list.append((j, k))

        return best_solution, best_cost

    def compute_cost(self, route, solution):
        cost = 0
        for i in range(len(route)):
            cost += self.matrix[route[solution[i - 1]][0]][route[solution[i]][0]]
        return cost

    def reorder_solution(self, route, solution):
        # Find the index of the depot (node 0) in the solution
        index = solution.index(route.index(self.depot))

        # Return the reordered solution
        return solution[index + 1:] + solution[:index]
