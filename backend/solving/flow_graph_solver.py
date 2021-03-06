"""
A solver based on the elaboration of a flow graph to quantify interfaces, connected by flow or scale relationships.
It is assumed that other kinds of relationship (part-of, upscale, ...) are translated into these two basic ones.
Another type of relationship considered is linear transform from InterfaceType to InterfaceType, which is cascaded into
appearances of its instances.

Before the elaboration of flow graphs, several preparatory steps:
* Find the separate contexts. Each context is formed by the "local", "environment" and "external" sets of processors,
  and is -totally- isolated from other contexts
  - Context defining attributes are defined in the Problem Statement command. If not, defined, a "context" attribute in
    Processors would be assumed
    If nothing is found, all Processors are assumed to be under the same context (what will happen??!!)
  - Elaborate (add necessary entities) the "environment", "external" top level processors if none have been specified.
    - Opposite processor can be specified when defining Interface
      - This attribute is taken into account if NO relationship originates or ends in this Interface. Then, a default
        relationship would be created
      - If Processors are defined for environment or
* Unexecuted model parts
  - Connection of Interfaces
  - Dataset expansion
* [Datasets]
* Scenarios
  - Parameters
* Time. Clasify QQs by time, on storage
* Observers (different versions). Take average always

"""
from collections import namedtuple

#import matplotlib.pyplot as plt
import networkx as nx
from typing import Dict, List, Set, Any, Tuple, Union, Optional, NamedTuple

from backend import case_sensitive, ureg
from backend.command_generators.parser_ast_evaluators import ast_evaluator
from backend.command_generators.parser_field_parsers import string_to_ast, expression_with_parameters, is_year, is_month
from backend.common.helper import create_dictionary, PartialRetrievalDictionary, ifnull, Memoize
from backend.models.musiasem_concepts import ProblemStatement, Parameter, FactorsRelationDirectedFlowObservation, \
    FactorTypesRelationUnidirectionalLinearTransformObservation, FactorsRelationScaleObservation, Processor, \
    FactorQuantitativeObservation, Factor, ProcessorsRelationPartOfObservation, ProcessorsRelationUpscaleObservation
from backend.model_services import get_case_study_registry_objects, State
from backend.models.musiasem_concepts_helper import find_quantitative_observations
from backend.solving.graph.computation_graph import ComputationGraph
from backend.solving.graph.flow_graph import FlowGraph


@Memoize
def get_processor_name(processor: Processor, registry: PartialRetrievalDictionary) -> str:
    """ Get the processor hierarchical name with caching enabled """
    return processor.full_hierarchy_names(registry)[0]


def get_interface_name(interface: Factor, registry: PartialRetrievalDictionary) -> str:
    """ Get the full interface name prefixing it with the processor hierarchical name """
    return get_processor_name(interface.processor, registry) + ":" + interface.name


def get_circular_dependencies(parameters: Dict[str, Tuple[Any, list]]) -> list:
    # Graph, for evaluation of circular dependencies
    G = nx.DiGraph()
    for param, (_, dependencies) in parameters.items():
        for param2 in dependencies:
            G.add_edge(param2, param)  # We need "param2" to obtain "param"
    return list(nx.simple_cycles(G))


def evaluate_parameters_for_scenario(base_params: List[Parameter], scenario_params: Dict[str, str]):
    """
    Obtain a dictionary (parameter -> value), where parameter is a string and value is a literal: number, boolean,
    category or string.

    Start from the base parameters then overwrite with the values in the current scenario.

    Parameters may depend on other parameters, so this has to be considered before evaluation.
    No cycles are allowed in the dependencies, i.e., if P2 depends on P1, P1 cannot depend on P2.
    To analyze this, first expressions are evaluated, extracting which parameters appear in each of them. Then a graph
    is elaborated based on this information. Finally, an algorithm to find cycles is executed.

    :param base_params:
    :param scenario_params:
    :return:
    """
    # Create dictionary without evaluation
    result_params = create_dictionary()
    result_params.update({p.name: p.default_value for p in base_params if p.default_value})

    # Overwrite with scenario expressions or constants
    result_params.update(scenario_params)

    state = State()
    known_params = create_dictionary()
    unknown_params = create_dictionary()

    # Now, evaluate ALL expressions
    for param, expression in result_params.items():
        value, ast, params, issues = evaluate_numeric_expression_with_parameters(expression, state)
        if not value:  # It is not a constant, store the parameters on which this depends
            if case_sensitive:
                unknown_params[param] = (ast, set(params))
            else:
                unknown_params[param] = (ast, set([p.lower() for p in params]))
        else:  # It is a constant, store it
            result_params[param] = value  # Overwrite
            known_params[param] = value

    cycles = get_circular_dependencies(unknown_params)
    if len(cycles) > 0:
        raise Exception(f"Parameters cannot have circular dependencies. {len(cycles)} cycles were detected: "
                        f"{':: '.join(cycles)}")

    # Initialize state with known parameters
    state.update(known_params)

    # Loop until no new parameters can be evaluated
    previous_len_unknown_params = len(unknown_params) + 1
    while len(unknown_params) < previous_len_unknown_params:
        previous_len_unknown_params = len(unknown_params)

        for param in list(unknown_params):  # A list(...) is used because the dictionary can be modified inside
            ast, params = unknown_params[param]
            if params.issubset(known_params):
                value, _, _, issues = evaluate_numeric_expression_with_parameters(ast, state)
                if not value:
                    raise Exception(f"It should be possible to evaluate the parameter '{param}'. "
                                    f"Issues: {', '.join(issues)}")
                else:
                    del unknown_params[param]
                    result_params[param] = value
                    state.set(param, value)

    if len(unknown_params) > 0:
        raise Exception(f"Could not evaluate the following parameters: {', '.join(unknown_params)}")

    return result_params


def prepare_interfaces_graph(factors: List[Factor]) -> nx.DiGraph:
    """
    Construct a DiGraph JUST with NODES, which are ALL the Factors

    :param factors:
    :return: a DiGraph
    """

    G = nx.DiGraph()
    for f in factors:
        # d = dict(interface=f)
        # G.add_node(f, **d)
        G.add_node(f)
    return G


def create_scales_graph(scale_relations: List[FactorsRelationScaleObservation]) -> nx.DiGraph:
    """
    This graph is used to put interfaces into scale, possibly in cascade (an Interface should not receive more than one scale).
    The scaling can then be updated for each scenario (parameters) and values can depend also on the TIME-PERIOD.
    Interfaces not involved in the graph may be removed from it.

    ADDITIONAL METHOD (set_update_scales_graph):
    * Set values, parameters, and evaluate scale expression. Initial values in the middle of a scaling chain are rejected.
      Only allowed at the beginning of a scale chain. The "scale_origin" property is set for nodes starting one of these chains.
    * Solve scales

    :param scale_relations:
    :return: nx.DiGraph (with the "scales graph")
    """
    G = nx.DiGraph()  # Start a graph

    # Auxiliary sets:
    # - "origin" only (origin-destination) nodes are sources for scale.
    # - "destination" nodes can only appear once as destination
    origin_interfaces: Set[Factor] = set()
    destination_interfaces: Set[Factor] = set()
    state = State()  # Empty State, just to be able to evaluate expressions and detect needed parameters

    for relation in scale_relations:
        value, ast, _, issues = evaluate_numeric_expression_with_parameters(relation.quantity, state)
        if value:
            ast = None

        assert(len(issues) == 0)

        # Add an edge per i2i scale relation
        G.add_edge(relation.origin, relation.destination, rel=relation, ast=ast, value=value)

        # Nodes appearing in scale are not to be removed
        # G[s.origin]["remove"] = False
        # G[s.destination]["remove"] = False

        # Nodes appearing more than once as destination is a construction error
        if relation.destination in destination_interfaces:
            raise Exception("An Interface should not appear in more than one Scale relation as destination")

        origin_interfaces.add(relation.origin)
        destination_interfaces.add(relation.destination)

    # "Beginning" nodes are marked
    nx.set_node_attributes(G, False, "beginning")
    for i in origin_interfaces.difference(destination_interfaces):
        G.nodes[i]["beginning"] = True

    return G


def get_scale_beginning_interfaces(graph: nx.DiGraph):
    return set([node for node, data in graph.nodes(data=True) if data["beginning"]])


def set_update_scales_graph(graph: nx.DiGraph, params: Dict[str, Any],
                            beginning_values: Dict[Factor, Tuple[Any, FactorQuantitativeObservation]]):
    """
    For a scaling graph:
     - set both the parameters and the values of Interfaces beginning scale-chains
     - update the scale chains accordingly

    :param graph: Graph with all scale chains
    :param params: Parameters to apply to values in edges and nodes of the graph
    :param beginning_values: Expressions (plus "unit") for beginning nodes of the graph
    :return: Nothing (the graph is updated in-place)
    """

    # Set of all nodes.
    all_interfaces = set(graph.nodes)
    # Set of "scale beginning" nodes.
    beginning_interfaces = get_scale_beginning_interfaces(graph)
    # Set of "scale following" nodes
    following_interfaces = all_interfaces.difference(beginning_interfaces)

    # Set of nodes with value
    interfaces_with_value = set(beginning_values.keys())

    # Check that all beginning interfaces have been defined (have a value)
    mandatory_to_define_all_beginning_interfaces = False

    if mandatory_to_define_all_beginning_interfaces:
        interfaces_which_should_have_a_value = beginning_interfaces.difference(interfaces_with_value)
        if interfaces_which_should_have_a_value:
            s = ", ".join([i.processor.name + ":" + i.name for i in interfaces_which_should_have_a_value])
            raise Exception("Not all scale beginning Interfaces have been assigned a value: "+s)

    # "following" interfaces in scale-chains should not have a value
    interfaces_which_should_not_have_a_value = following_interfaces.intersection(interfaces_with_value)

    if interfaces_which_should_not_have_a_value:
        s = ", ".join([i.processor.name + ":" + i.name for i in interfaces_which_should_not_have_a_value])
        raise Exception("Interfaces in scale chains cannot have assigned values: "+s)

    # Now expressions. First, prepare "state"
    state = State()
    state.update(params)

    # Evaluate (AST) all expressions from the INTERSECTION
    defined_beginning_interfaces = beginning_interfaces.intersection(interfaces_with_value)
    for i in defined_beginning_interfaces:
        expression = beginning_values[i][0]
        unit = ureg(beginning_values[i][1].attributes["unit"])
        v, _, _, issues = evaluate_numeric_expression_with_parameters(expression, state)
        if not v:
            raise Exception(f"Could not evaluate expression '{expression}': {', '.join(issues)}")
        else:
            graph.nodes[i]["value"] = v * unit

    # Evaluate all edges
    for u, v, data in graph.edges(data=True):
        ast = data["ast"]
        if ast:
            v, _, _, issues = evaluate_numeric_expression_with_parameters(ast, state)
            if not v:
                raise Exception(f"Could not evaluate edge scale expression '{ast}' for edge ({u.name}->{v.name}): {', '.join(issues)}")
            else:
                graph.edges[u, v]["value"] = v

    # Now, compute values in nodes
    def compute_scaled_nodes(nodes):
        for i in nodes:
            val = graph.nodes[i]["value"]
            tmp = []
            for suc in graph.successors(i):
                # TODO Consider unit conversions, or the unit of the predecessor is inherited?
                graph.nodes[suc]["value"] = graph.nodes[i]["value"] * graph.edges[i, suc]["value"]
                tmp.append(suc)
            compute_scaled_nodes(tmp)

    compute_scaled_nodes(defined_beginning_interfaces)


def get_observations_OLD(prd: PartialRetrievalDictionary) \
        -> Tuple[PartialRetrievalDictionary, PartialRetrievalDictionary, Dict[str, int]]:
    """
    Process All QQ observations (intensive or extensive):
    * Store in a compact way (then clear), by Time-period, by Interface, by Observer.
    * Convert to float or prepare AST
    * Store as value the result plus the QQ observation (in a tuple)

    :param prd:
    :param relative: True->a QQ observation relative to the value of another interface
    :return: another PartialRetrievalDictionary, the Observers and the Time Periods (indexed)
    """
    observations_prd = PartialRetrievalDictionary()
    relative_observations_prd = PartialRetrievalDictionary()
    time_periods: Dict[str, int] = create_dictionary()  # Dictionary of time periods and the associated IDX
    state = State()

    next_time_period_idx = 0
    for observation in find_quantitative_observations(prd, processor_instances_only=True):

        # Obtain time period index
        time = observation.attributes["time"]
        if time not in time_periods:
            time_periods[time] = next_time_period_idx
            next_time_period_idx += 1

        # Elaborate Key: Interface, Time, Observer
        key = dict(__i=observation.factor, __t=time_periods[time], __o=observation.observer)

        value, ast, _, issues = evaluate_numeric_expression_with_parameters(observation.value, state)
        if not value:
            value = ast

        # Store Key: (Value, FactorQuantitativeObservation)
        if observation.is_relative:
            relative_observations_prd.put(key, (value, observation))
        else:
            observations_prd.put(key, (value, observation))

    return observations_prd, relative_observations_prd, time_periods


TimeObservationsType = Dict[str, List[Tuple[float, FactorQuantitativeObservation]]]


def get_observations_by_time(prd: PartialRetrievalDictionary) -> Tuple[TimeObservationsType, TimeObservationsType]:
    """
    Process All QQ observations (intensive or extensive):
    * Store in a compact way (then clear), by Time-period, by Interface, by Observer.
    * Convert to float or prepare AST
    * Store as value the result plus the QQ observation (in a tuple)

    :param prd:
    :return:
    """
    observations: Dict[str, List[Tuple[float, FactorQuantitativeObservation]]] = {}
    state = State()

    # Get all observations by time
    for observation in find_quantitative_observations(prd, processor_instances_only=True):

        # Try to evaluate the observation value
        value, ast, _, issues = evaluate_numeric_expression_with_parameters(observation.value, state)

        # Store: (Value, FactorQuantitativeObservation)
        time = observation.attributes["time"]
        if time not in observations:
            observations[time] = []

        observations[time].append((ifnull(value, ast), observation))

    # Check all time periods are consistent. All should be Year or Month, but not both.
    time_period_type = get_type_from_all_time_periods(list(observations.keys()))
    assert(time_period_type in ["Year", "Month"])

    # Remove generic period type and insert it into all specific periods. E.g. "Year" into "2010", "2011" and "2012"
    if time_period_type in observations:
        # Generic monthly ("Month") or annual ("Year") data
        periodic_observations = observations[time_period_type]
        del observations[time_period_type]

        for time in observations:
            observations[time] += periodic_observations

    return split_observations_by_relativeness(observations)


def evaluate_numeric_expression_with_parameters(expression: Union[float, str, dict], state: State) \
        -> Tuple[Optional[float], Optional[Dict], Set, List[str]]:

    issues: List[Tuple[int, str]] = []
    ast = None
    value = None
    params = set()

    if not expression:
        value = None

    elif isinstance(expression, float):
        value = expression

    elif isinstance(expression, dict):
        ast = expression
        value, params = ast_evaluator(ast, state, None, issues)
        if value:
            ast = None

    elif isinstance(expression, str):
        try:
            value = float(expression)
        except ValueError:
            ast = string_to_ast(expression_with_parameters, expression)
            value, params = ast_evaluator(ast, state, None, issues)
            if value:
                ast = None

    else:
        issues.append((3, "Invalid type for expression"))

    return value, ast, params, [i[1] for i in issues]


def get_scaled(scenarios, scenario_params, relations_scale, observations_by_time):

    # Obtain a i2i Scales Graph
    graph = create_scales_graph(relations_scale)

    # Compute the scales for the different scenarios and time periods, and store the results in
    # another partial retrieval dictionary
    scale_beginning_interfaces = get_scale_beginning_interfaces(graph)

    scales_prd = PartialRetrievalDictionary()
    for scenario_idx, scenario_name in enumerate(scenarios):

        for time_period, observations in observations_by_time.items():

            # Filter, and prepare dictionary for the update of the scaling
            beginning_values: Dict[Factor, Tuple[Any, FactorQuantitativeObservation]] = \
                {obs.factor: (value, obs) for value, obs in observations if obs.factor in scale_beginning_interfaces}

            # Evaluate expressions
            set_update_scales_graph(graph, scenario_params[scenario_name], beginning_values)

            # Write data to the PartialRetrieveDictionary
            for interface, data in graph.nodes(data=True):  # type: Factor, Dict
                key = dict(__i=interface, __t=time_period, __s=scenario_idx)
                scales_prd.put(key, (interface, data["value"]))  # ERROR: Observation not hashable

    return scales_prd


def get_type_from_all_time_periods(time_periods: List[str]) -> Optional[str]:
    """ Check if all time periods are of the same period type, either Year or Month:
         - general "Year" & specific year (YYYY)
         - general "Month" & specific month (mm-YYYY or YYYY-mm, separator can be any of "-/")

    :param time_periods:
    :return:
    """
    # Based on the first element we will check the rest of elements
    period = next(iter(time_periods))

    if period == "Year" or is_year(period):
        period_type = "Year"
        period_check = is_year
    elif period == "Month" or is_month(period):
        period_type = "Month"
        period_check = is_month
    else:
        return None

    for time_period in time_periods:
        if time_period != period_type and not period_check(time_period):
            return None

    return period_type


def split_observations_by_relativeness(observations_by_time: TimeObservationsType):
    observations_by_time_norelative = {}
    observations_by_time_relative = {}
    for time, observations in observations_by_time.items():
        observations_by_time_norelative[time] = []
        observations_by_time_relative[time] = []
        for value, obs in observations:
            if obs.is_relative:
                observations_by_time_relative[time].append((value, obs))
            else:
                observations_by_time_norelative[time].append((value, obs))

    return observations_by_time_norelative, observations_by_time_relative


def weakly_connected_subgraph(graph: nx.DiGraph, node: str) -> Optional[nx.graphviews.subgraph_view]:
    for component in nx.weakly_connected_components(graph):  # type: Set
        if node in component:
            return graph.subgraph(component)
    else:
        return None


def flow_graph_solver(global_parameters: List[Parameter], problem_statement: ProblemStatement,
                      input_systems: Dict[str, Set[Processor]], state: State):
    """
    * First scales have to be solved
    * Second direct flows
    * Third conversions of flows

    Once flows have been found, Indicators have to be gathered.

    :param global_parameters: Parameters including the default value (if defined)
    :param problem_statement: ProblemStatement object, with scenarios (parameters changing the default)
                              and parameters for the solver
    :param state: State with everything
    :param input_systems: A dictionary of the different systems to be solved
    :return: Issue[]
    """

    class Edge(NamedTuple):
        src: Factor
        dst: Factor
        weight: Optional[str]

    def add_edges(edges: List[Edge]):
        for src, dst, weight in edges:
            src_name = get_interface_name(src, glb_idx)
            dst_name = get_interface_name(dst, glb_idx)
            if "Archetype" in [src.processor.instance_or_archetype, dst.processor.instance_or_archetype]:
                print(f"WARNING: excluding relation from '{src_name}' to '{dst_name}' because of Archetype processor")
            else:
                relations.add_edge(src_name, dst_name, weight=weight)

    glb_idx, _, _, _, _ = get_case_study_registry_objects(state)

    # Get all interface observations. Also resolve expressions without parameters. Cannot resolve expressions
    # depending only on global parameters because some of them can be overridden by scenario parameters.
    time_observations_absolute, time_observations_relative = get_observations_by_time(glb_idx)

    if len(time_observations_absolute) == 0:
        raise Exception(f"No absolute observations have been found. The solver has nothing to solve.")

    relations = nx.DiGraph()

    # Add Interfaces -Flow- relations (time independent)
    add_edges([Edge(r.source_factor, r.target_factor, r.weight)
               for r in glb_idx.get(FactorsRelationDirectedFlowObservation.partial_key())])

    # Add Processors -Scale- relations (time independent)
    add_edges([Edge(r.origin, r.destination, r.quantity)
               for r in glb_idx.get(FactorsRelationScaleObservation.partial_key())])

    # TODO Expand flow graph with it2it transforms
    # relations_scale_it2it = glb_idx.get(FactorTypesRelationUnidirectionalLinearTransformObservation.partial_key())

    # First pass to resolve weight expressions: only expressions without parameters can be solved
    for _, _, data in relations.edges(data=True):
        expression = data["weight"]
        if expression:
            value, ast, _, _ = evaluate_numeric_expression_with_parameters(expression, state)
            data["weight"] = ifnull(value, ast)

    for scenario_idx, (scenario_name, scenario_params) in enumerate(problem_statement.scenarios.items()):

        print(f"********************* SCENARIO: {scenario_name}")

        scenario_state = State()
        scenario_combined_params = evaluate_parameters_for_scenario(global_parameters, scenario_params)
        scenario_state.update(scenario_combined_params)

        for time_period, observations in time_observations_absolute.items():

            print(f"********************* TIME PERIOD: {time_period}")

            # Final values are taken from "observations" that need to computed
            graph_params = {}

            # Second and last pass to resolve observation expressions with parameters
            for expression, obs in observations:
                interface_name = get_interface_name(obs.factor, glb_idx)
                if interface_name not in relations.nodes:
                    print(f"WARNING: observation at interface '{interface_name}' is not taken into account.")
                else:
                    value, ast, _, issues = evaluate_numeric_expression_with_parameters(expression, scenario_state)
                    if not value:
                        raise Exception(f"Cannot evaluate expression '{expression}' for observation at "
                                        f"interface '{interface_name}'. Issues: {', '.join(issues)}")
                    graph_params[interface_name] = value

            assert(graph_params is not None)

            # Add Processors internal -RelativeTo- relations (time dependent)
            # Transform relative observations into graph edges
            for expression, obs in time_observations_relative[time_period]:
                relations.add_edge(get_interface_name(obs.relative_factor, glb_idx),
                                   get_interface_name(obs.factor, glb_idx),
                                   weight=expression)

            # Second and last pass to resolve weight expressions: expressions with parameters can be solved
            for u, v, data in relations.edges(data=True):
                expression = data["weight"]
                if expression:
                    value, ast, _, _ = evaluate_numeric_expression_with_parameters(expression, scenario_state)
                    if not value:
                        raise Exception(f"Cannot evaluate expression '{expression}' for weight "
                                        f"from interface '{u}' to interface '{v}'. Issues: {', '.join(issues)}")
                    data["weight"] = value

            # ----------------------------------------------------

            if time_period == '2008':
                for component in nx.weakly_connected_components(relations):
                    nx.draw_kamada_kawai(relations.subgraph(component), with_labels=True)
                    plt.show()

            flow_graph = FlowGraph(relations)
            comp_graph, issues = flow_graph.get_computation_graph()

            for issue in issues:
                print(issue)

            print(f"****** NODES: {comp_graph.nodes}")

            # ----------------------------------------------------

            # Obtain nodes without a value
            compute_nodes = [n for n in comp_graph.nodes if not graph_params.get(n)]

            # Compute the missing information with the computation graph
            if len(compute_nodes) == 0:
                print("All nodes have a value. Nothing to solve.")
                return []

            print(f"****** UNKNOWN NODES: {compute_nodes}")
            print(f"****** PARAMS: {graph_params}")

            conflicts = comp_graph.compute_param_conflicts(set(graph_params.keys()))

            for s, (param, values) in enumerate(conflicts.items()):
                print(f"Conflict {s + 1}: {param} -> {values}")

            combinations = ComputationGraph.compute_param_combinations(conflicts)

            for s, combination in enumerate(combinations):
                print(f"Combination {s}: {combination}")

                filtered_params = {k: v for k, v in graph_params.items() if k in combination}
                results, _ = comp_graph.compute_values(compute_nodes, filtered_params)

                results_with_values = {k: v for k, v in results.items() if v}
                print(f'  results_with_values={results_with_values}')

                # TODO: work with "part_of_graph"
                #  - Params: graph_params + results
                #  - Compute conflicts, combinations
                #  - For each combination "compute_values"


        # TODO INDICATORS

    # ----------------------------------------------------
    # ACCOUNTING PER SYSTEM

    for system in input_systems:

        # Handle Processors -PartOf- relations
        proc_hierarchy = nx.DiGraph()
        for relation in glb_idx.get(ProcessorsRelationPartOfObservation.partial_key()):  # type: ProcessorsRelationPartOfObservation
            if relation.parent_processor.instance_or_archetype == "Instance":
                proc_hierarchy.add_edge(get_processor_name(relation.child_processor, glb_idx), get_processor_name(relation.parent_processor, glb_idx))

        part_of_graph = ComputationGraph()

        # for relation in system_flows[system]:  # type: FactorsRelationDirectedFlowObservation
        #
        #     # We create another graph only with interfaces in processors with parents
        #     for interface in [relation.source_factor, relation.target_factor]:
        #
        #         processor_name = get_processor_name(interface.processor, glb_idx)
        #         interface_full_name = processor_name+":"+interface.name
        #
        #         # If "processor" is in the "PartOf" hierarchy AND the "processor:interface" is not being handled yet
        #         if processor_name in proc_hierarchy and interface_full_name not in part_of_graph.nodes:
        #             # Insert into the Computation Graph a copy of the "PartOf" hierarchy of processors
        #             # for the specific interface
        #             new_edges = [(u+":"+interface.name, v+":"+interface.name)
        #                          for u, v in weakly_connected_subgraph(proc_hierarchy, processor_name).edges]
        #             part_of_graph.add_edges(new_edges, 1.0, None)

        # for component in nx.weakly_connected_components(part_of_graph.graph):
        #     nx.draw_kamada_kawai(part_of_graph.graph.subgraph(component), with_labels=True)
        #     plt.show()

    return []
