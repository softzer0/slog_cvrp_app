import random
from time import time
import numpy as np

from .tabu import Tabu


# =========================================================================== GENETIC ALGORITHM =======================================
# Class to represent problems to be solved by means of a general
# genetic algorithm. It includes the following attributes:
# - genes: list of possible genes in a chromosome
# - individuals_length: length of each chromosome
# - decode: method that receives the genotype (chromosome) as input and returns
#    the phenotype (solution to the original problem represented by the chromosome)
# - fitness: method that returns the evaluation of a chromosome (acts over the
#    genotype)
# - mutation: function that implements a mutation over a chromosome
# - crossover: function that implements the crossover operator over two chromosomes
# =====================================================================================================================================

class CVRP:
    def __init__(self, max_capacity, matrix, nodes):
        self.max_capacity = max_capacity
        self.matrix = matrix
        self.nodes = nodes
        self.depot = (len(nodes)-1, 0)
        self.tabu = Tabu(matrix, self.depot)

    class Problem_Genetic:
        def __init__(self, parent, genes, fitness, decode):
            self.parent = parent
            self.genes = genes
            self.fitness = fitness
            self.decode = decode

        def crossover(self, parent1, parent2):
            def process_gen_repeated(copy_child1, copy_child2):
                count1 = 0
                for gen1 in copy_child1[:pos]:
                    repeat = copy_child1.count(gen1)
                    if repeat > 1 and gen1[0] == self.parent.depot[0]:
                        repeat = 0
                    if repeat > 1:  # If need to fix repeated gen
                        count2 = 0
                        for gen2 in parent1[pos:]:  # Choose next available gen
                            if gen2 not in copy_child1:
                                child1[count1] = parent1[pos:][count2]
                            count2 += 1
                    count1 += 1

                count1 = 0
                for gen1 in copy_child2[:pos]:
                    repeat = copy_child2.count(gen1)
                    if repeat > 1 and gen1[0] == self.parent.depot[0]:
                        repeat = 0
                    if repeat > 1:  # If need to fix repeated gen
                        count2 = 0
                        for gen2 in parent2[pos:]:  # Choose next available gen
                            if gen2 not in copy_child2:
                                child2[count1] = parent2[pos:][count2]
                            count2 += 1
                    count1 += 1

                return [[child1, np.inf], [child2, np.inf]]

            pos = random.randrange(1, len(self.parent.nodes))
            child1 = parent1[:pos] + parent2[pos:]
            child2 = parent2[:pos] + parent1[pos:]

            return process_gen_repeated(child1, child2)

    def fitnessVRP(self, chromosome):
        new_chromosome = []
        fitness_value = 0
        cap = 0
        route = [self.depot]
        for i in range(len(chromosome[0])):
            cap += chromosome[0][i][1]
            route.append(chromosome[0][i])
            if i + 1 == len(chromosome[0]) or cap + chromosome[0][i + 1][1] > self.max_capacity:
                solution, distance = self.tabu.execute(route, 5)
                solution = self.tabu.reorder_solution(route, solution)
                new_chromosome += list(map(lambda p: route[p], solution))
                fitness_value += distance
                # if i+1 == len(chromosome[0]):
                #     break
                cap = 0
                route = [self.depot]
        if fitness_value <= chromosome[1]:
            chromosome[0] = new_chromosome
            chromosome[1] = fitness_value
        return chromosome[1]

    def decodeVRP(self, chromosome):
        c_res = []
        cap = 0
        route = [self.depot[0]]
        for i in range(len(chromosome[0])):
            cap += chromosome[0][i][1]
            route.append(chromosome[0][i][0])
            if i+1 == len(chromosome[0]) or cap + chromosome[0][i+1][1] > self.max_capacity:
                route.append(self.depot[0])
                c_res.append(route)
                # if i+1 == len(chromosome[0]):
                #     break
                cap = 0
                route = [self.depot[0]]
        return c_res

    # ========================================================== FIRST PART: GENETIC OPERATORS============================================
    # Here We defined the requierements functions that the GA needs to work
    # The function receives as input:
    # * problem_genetic: an instance of the class Problem_Genetic, with
    #     the optimization problem that we want to solve.
    # * k: number of participants on the selection tournaments.
    # * opt: max or min, indicating if it is a maximization or a
    #     minimization problem.
    # * ngen: number of generations (halting condition)
    # * size: number of individuals for each generation
    # * ratio_cross: portion of the population which will be obtained by
    #     means of crossovers.
    # * prob_mutate: probability that a gene mutation will take place.
    # =====================================================================================================================================


    def genetic_algorithm_t(self, Problem_Genetic, k, opt, ngen, size, ratio_cross):  # , prob_mutate
        def initial_population(Problem_Genetic, size):
            def generate_chromosome():
                chromosome_copy = Problem_Genetic.genes.copy()
                random.shuffle(chromosome_copy)
                return chromosome_copy

            return [[generate_chromosome(), np.inf] for _ in range(size)]

        def new_generation_t(Problem_Genetic, k, opt, population, n_parents, n_directs):  # , prob_mutate
            def tournament_selection(Problem_Genetic, population, n, k, opt):
                winners = []
                for _ in range(n):
                    elements = random.sample(population, k)
                    winners.append(opt(elements, key=Problem_Genetic.fitness))
                return winners

            def cross_parents(Problem_Genetic, parents):
                childs = []
                for i in range(0, len(parents), 2):
                    childs.extend(Problem_Genetic.crossover(parents[i][0], parents[i + 1][0]))
                return childs

            directs = tournament_selection(Problem_Genetic, population, n_directs, k, opt)
            crosses = cross_parents(Problem_Genetic,
                                    tournament_selection(Problem_Genetic, population, n_parents, k, opt))
            # mutations = mutate(Problem_Genetic, crosses, prob_mutate)
            new_generation = directs + crosses  # + mutations

            return new_generation

        population = initial_population(Problem_Genetic, size)
        n_parents = round(size * ratio_cross)
        n_parents = (n_parents if n_parents % 2 == 0 else n_parents - 1)
        n_directs = size - n_parents

        for _ in range(ngen):
            population = new_generation_t(Problem_Genetic, k, opt, population, n_parents, n_directs)  # , prob_mutate

        bestChromosome = opt(population, key=Problem_Genetic.fitness)
        print(f'Chromosome: {bestChromosome}')
        genotype = Problem_Genetic.decode(bestChromosome)
        # print(f'Solution: {genotype[0]}')

        return bestChromosome, genotype

    # ================================================THIRD PART: EXPERIMENTATION=========================================================
    # Run over the same instances both the standard GA (from first part) as well as the modified version (from second part).
    # Compare the quality of their results and their performance. Due to the inherent randomness of GA, the experiments performed over each instance should be run several times.
    # ====================================================================================================================================

    # ----------------------------------------MAIN PROGRAMA PRINCIPAL--------------------------------

    def start(self, k):
        print(f'Executing {k} VRP instances...')
        genes = [(i, int(self.nodes[i][1])) for i in range(len(self.nodes)-1)]
        VRP_PROBLEM = self.Problem_Genetic(self, genes, self.fitnessVRP, self.decodeVRP)
        tiempo_inicial_t2 = time()
        genotypes = {}
        for _ in range(k):
            result = self.genetic_algorithm_t(VRP_PROBLEM, 2, min, 200, 100, 0.85)
            genotypes[result[0][1]] = (result[0], result[1])

        best = min(list(genotypes.keys()))
        print(f'Best result: {genotypes[best][0]}')

        tiempo_final_t2 = time()
        print(f'Total time: {(tiempo_final_t2 - tiempo_inicial_t2)} secs.')

        return genotypes[best][1]
