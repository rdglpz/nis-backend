from typing import Union, List, Tuple, Optional

from backend.common.helper import PartialRetrievalDictionary, strcmp
from backend.model_services import State, get_case_study_registry_objects
from backend.model.memory.musiasem_concepts import \
    FlowFundRoegenType, FactorInProcessorType, RelationClassType, allowed_ff_types, \
    Processor, FactorType, Observer, Factor, \
    ProcessorsRelationPartOfObservation, ProcessorsRelationUndirectedFlowObservation, \
    ProcessorsRelationUpscaleObservation, \
    FactorsRelationDirectedFlowObservation, Hierarchy, Taxon, QualifiedQuantityExpression, \
    FactorQuantitativeObservation


def hierarchical_name_variants(h_name: str):
    """
    Given a hierarchical name, obtain variants

    :param h_name:
    :return: An ordered list of names that may refer to the same object
    """
    parts = h_name.split(".")
    if len(parts) > 1:
        return [h_name, parts[-1]]
    else:
        return [h_name]  # A simple name


def find_observable_by_name(name: str, idx: PartialRetrievalDictionary, processor: Processor = None,
                            factor_type: FactorType = None) -> Union[Factor, Processor, FactorType]:
    """
    From a full Factor name "processor:factortype", obtain the corresponding Factor, searching in the INDEX of objects
    It supports also finding a Processor: "processor" (no ":factortype" part)
    It supports also finding a FactorType: ":factortype" (no "processor" part)
    It considers the fact that both Processors and FactorTypes can have different names
    (and consequently that Factors can have also multiple names)

    :param name: ":" separated processor name and factor type name. "p:ft" returns a Factor.
                 "p" or "p:" returns a Processor. ":ft" returns a FactorType
    :param idx: The PartialRetrievalDictionary where the objects have been previously indexed
    :param processor: Already resolved Processor. If ":ft" is specified, it will use this parameter to return a Factor
                 (not a FactorType)
    :param factor_type: Already resolved FactorType. If "p:" is specified (note the ":") , it will use this parameter
                 to return a Factor (not a Processor)
    :return: Processor or FactorType or Factor
    """
    res = None
    if isinstance(name, str):
        s = name.split(":")
        if len(s) == 2:  # There is a ":"
            p_name = s[0]
            f_name = s[1]
            if not p_name:  # Processor can be blank
                p_name = None
            if not f_name:  # Factor type can be blank
                f_name = None
        elif len(s) == 1:  # If no ":", go just for the processor
            p_name = s[0]
            f_name = None
        # Retrieve the processor
        if p_name:
            for alt_name in hierarchical_name_variants(p_name):
                p = idx.get(Processor.partial_key(name=alt_name))
                if p:
                    p = p[0]
                    break
        elif processor:
            p = processor
        else:
            p = None

        # Retrieve the FactorType
        if f_name:
            for alt_name in hierarchical_name_variants(f_name):
                ft = idx.get(FactorType.partial_key(name=alt_name))
                if ft:
                    ft = ft[0]
                    break
        elif factor_type:
            ft = factor_type
        else:
            res = p
            ft = None

        # Retrieve the Factor
        if not p_name and not p:  # If no Processor available at this point, FactorType is being requested, return it
            res = ft
        elif not res and p and ft:
            f = idx.get(Factor.partial_key(processor=p, factor_type=ft))
            if f:
                res = f[0]
    else:
        res = name

    return res


def find_or_create_observable(state: Union[State, PartialRetrievalDictionary],
                              name: str, source: Union[str, Observer]=Observer.no_observer_specified,
                              aliases: str=None,  # "name" (processor part) is an alias of "aliases" Processor
                              proc_external: bool=None, proc_attributes: dict=None, proc_location=None,
                              fact_roegen_type: FlowFundRoegenType=None, fact_attributes: dict=None,
                              fact_incoming: bool=None, fact_external: bool=None, fact_location=None):
    """
    Find or create Observables: Processors, Factor and FactorType objects
    It can also create an Alias for a Processor if the name of the aliased Processor is passed (parameter "aliases")

    "name" is parsed, which can specify a processor AND a factor, both hierarchical ('.'), separated by ":"

    :param state:
    :param name: Full name of processor, processor':'factor or ':'factor
    :param source: Name of the observer or Observer itself (used only when creating nested Processors, because it implies part-of relations)
    :param aliases: Full name of an existing processor to be aliased by the processor part in "name"
    :param proc_external: True=external processor; False=internal processor
    :param proc_attributes: Dictionary with attributes to be added to the processor if it is created
    :param proc_location: Specification of where the processor is physically located, if it applies
    :param fact_roegen_type: Flow or Fund
    :param fact_attributes: Dictionary with attributes to be added to the Factor if it is created
    :param fact_incoming: True if the Factor is incoming regarding the processor; False if it is outgoing
    :param fact_external: True if the Factor comes from Environment
    :param fact_location: Specification of where the processor is physically located, if it applies
    :return: Processor, FactorType, Factor
    """

    # Decompose the name
    p_names, f_names = _obtain_name_parts(name)

    # Get objects from state
    if isinstance(state, PartialRetrievalDictionary):
        glb_idx = state
    else:
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)

    # Get the Observer for the relations (PART-OF for now)
    if source:
        if isinstance(source, Observer):
            oer = source
        else:
            oer = glb_idx.get(Observer.partial_key(name=source))
            if not oer:
                oer = Observer(source)
                glb_idx.put(oer.key(), oer)
            else:
                oer = oer[0]

    result = None
    p = None  # Processor to which the Factor is connected
    ft = None  # FactorType
    f = None  # Factor

    if p_names and aliases:
        # Create an alias for the Processor
        if isinstance(aliases, str):
            p = glb_idx.get(Processor.partial_key(aliases))
        elif isinstance(aliases, Processor):
            p = aliases
        if p:
            full_name = ".".join(p_names)
            # Look for a processor named <full_name>, it will be an AMBIGUITY TO BE AVOIDED
            p1, k1 = glb_idx.get(Processor.partial_key(full_name), True)
            if p1:
                # If it is an ALIAS, void the already existing because there would be no way to decide
                # which of the two (or more) do we need
                if Processor.is_alias_key(k1[0]):
                    # Assign NONE to the existing Alias
                    glb_idx.put(k1[0], None)
            else:
                # Create the ALIAS
                k_ = Processor.alias_key(full_name, p)
                glb_idx.put(k_, p)  # An alternative Key pointing to the same processor
    else:
        # Find or create the "lineage" of Processors, using part-of relation ("matryoshka" or recursive containment)
        parent = None
        acum_name = ""
        for i, p_name in enumerate(p_names):
            last = i == (len(p_names)-1)

            # CREATE processor(s) (if it does not exist). The processor is an Observable
            acum_name += ("." if acum_name != "" else "") + p_name
            p = glb_idx.get(Processor.partial_key(name=acum_name))
            if not p:
                attrs = proc_attributes if last else None
                location = proc_location if last else None
                p = Processor(acum_name,
                              external=proc_external,
                              location=location,
                              tags=None,
                              attributes=attrs
                              )
                # Index it, with its multiple names, adding the attributes only if it is the processor in play
                for alt_name in hierarchical_name_variants(acum_name):
                    p_key = Processor.partial_key(alt_name, p.ident)
                    if last and proc_attributes:
                        p_key.update({k: ("" if v is None else v) for k, v in proc_attributes.items()})
                    glb_idx.put(p_key, p)
            else:
                p = p[0]

            result = p

            if parent:
                # Create PART-OF relation
                o1 = glb_idx.get(ProcessorsRelationPartOfObservation.partial_key(parent=parent, child=p))
                if not o1:
                    o1 = ProcessorsRelationPartOfObservation.create_and_append(parent, p, oer)  # Part-of
                    glb_idx.put(o1.key(), o1)

            parent = p

    # Find or create the lineage of FactorTypes and for the last FactorType, find or create Factor
    parent = None
    acum_name = ""
    for i, ft_name in enumerate(f_names):
        last = i == len(f_names)-1

        # CREATE factor type(s) (if it does not exist). The Factor Type is a Class of Observables
        # (it is NOT observable: neither quantities nor relations)
        acum_name += ("." if acum_name != "" else "") + ft_name
        ft = glb_idx.get(FactorType.partial_key(name=acum_name))
        if not ft:
            attrs = fact_attributes if last else None
            ft = FactorType(acum_name,  #
                            parent=parent, hierarchy=None,
                            tipe=fact_roegen_type,  #
                            tags=None,  # No tags
                            attributes=attrs,
                            expression=None  # No expression
                            )
            for alt_name in hierarchical_name_variants(acum_name):
                ft_key = FactorType.partial_key(alt_name, ft.ident)
                if last and fact_attributes:
                    ft_key.update(fact_attributes)
                glb_idx.put(ft_key, ft)
        else:
            ft = ft[0]

        if last and p:  # The Processor must exist. If not, nothing is created or obtained
            # CREATE Factor (if it does not exist). An Observable
            f = glb_idx.get(Factor.partial_key(processor=p, factor_type=ft))
            if not f:
                f = Factor(acum_name,
                           p,
                           in_processor_type=FactorInProcessorType(external=fact_external, incoming=fact_incoming),
                           taxon=ft,
                           location=fact_location,
                           tags=None,
                           attributes=fact_attributes)
                glb_idx.put(f.key(), f)
            else:
                f = f[0]

            result = f

        parent = ft

    return p, ft, f  # Return all the observables (some may be None)
    # return result  # Return either a Processor or a Factor, to which Observations can be attached


def create_quantitative_observation(state: Union[State, PartialRetrievalDictionary],
                                    factor: Union[str, Factor],
                                    value: str, unit: str,
                                    observer: Union[str, Observer]=Observer.no_observer_specified,
                                    spread: str=None, assessment: str=None, pedigree: str=None, pedigree_template: str=None,
                                    relative_to: Union[str, Factor]=None,
                                    time: str=None,
                                    geolocation: str=None,
                                    comments: str=None,
                                    tags=None, other_attributes=None,
                                    proc_aliases: str=None,
                                    proc_external: bool=None, proc_attributes: dict=None, proc_location=None,
                                    ftype_roegen_type: FlowFundRoegenType=None, ftype_attributes: dict=None,
                                    fact_incoming: bool=None, fact_external: bool=None, fact_location=None):
    """
    Creates an Observation of a Factor
    If the Factor does not exist, it is created
    If no "value" is passed, only the Factor is created

    :param state:
    :param factor: string processor:factor_type or Factor
    :param value: expression with the value
    :param unit: metric unit
    :param observer: string with the name of the observer or Observer
    :param spread: expression defining uncertainty of :param value
    :param assessment:
    :param pedigree: encoded assessment of the quality of the science/technique of the observation
    :param pedigree_template: reference pedigree matrix used to encode the pedigree
    :param relative_to: Factor Type in the same Processor to which the value is relative
    :param time: time extent in which the value is valid
    :param geolocation: where the observation is
    :param comments: open comments about the observation
    :param tags: list of tags added to the observation
    :param other_attributes: dictionary added to the observation
    :param proc_aliases: name of aliased processor (optional). Used only if the Processor does not exist
    :param proc_external: True if the processor is outside the case study borders, False if it is inside. Used only if the Processor does not exist
    :param proc_attributes: Dictionary with attributes added to the Processor. Used only if the Processor does not exist
    :param proc_location: Reference specifying the location of the Processor. Used only if the Processor does not exist
    :param ftype_roegen_type: Either FUND or FLOW (applied to FactorType). Used only if the FactorType does not exist
    :param ftype_attributes: Dictionary with attributes added to the FactorType. Used only if the FactorType does not exist
    :param fact_incoming: Specifies if the Factor goes into or out the Processor. Used if the Factor (not FactorType) does not exist
    :param fact_external: Specifies if the Factor is injected from an external Processor. Used if the Factor (not FactorType) does not exist
    :param fact_location: Reference specifying the location of the Factor. Used if the Factor does not exist

    :return:
    """
    # Get objects from state
    if isinstance(state, State):
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
    elif isinstance(state, PartialRetrievalDictionary):
        glb_idx = state

    # Obtain factor
    p, ft = None, None
    if not isinstance(factor, Factor):
        p, ft, factor_ = find_or_create_observable(state,
                                                   factor,
                                                   # source=None,
                                                   aliases=proc_aliases,
                                                   proc_external=proc_external,
                                                   proc_attributes=proc_attributes,
                                                   proc_location=proc_location,
                                                   fact_roegen_type=ftype_roegen_type,
                                                   fact_attributes=ftype_attributes,
                                                   fact_incoming=fact_incoming,
                                                   fact_external=fact_external,
                                                   fact_location=fact_location
                                                   )
        if not isinstance(factor_, Factor):
            raise Exception("The name specified for the factor ('"+factor+"') did not result in the obtention of a Factor")
        else:
            factor = factor_

    # If a value is defined...
    if value:
        # Get the Observer for the relations (PART-OF for now)
        if isinstance(observer, Observer):
            oer = observer
        else:
            if not observer:
                observer = Observer.no_observer_specified
            oer = glb_idx.get(Observer.partial_key(name=observer))
            if not oer:
                oer = Observer(observer)
                glb_idx.put(oer.key(), oer)
            else:
                oer = oer[0]

        # Create the observation
        o = _create_quantitative_observation(factor,
                                             value, unit, spread, assessment, pedigree, pedigree_template,
                                             oer,
                                             relative_to,
                                             time,
                                             geolocation,
                                             comments,
                                             tags, other_attributes
                                             )
        # Register
        glb_idx.put(o.key(), o)

        # Return the observation
        return p, ft, factor, o
    else:
        # Return the Factor
        return p, ft, factor, None


def create_relation_observations(state: Union[State, PartialRetrievalDictionary],
                                 origin: Union[str, Processor, Factor],
                                 destinations: List[Tuple[Union[str, Processor, Factor], Optional[Tuple[Union[RelationClassType, str], Optional[str]]]]],
                                 relation_class: Union[str, RelationClassType]=None,
                                 oer: Union[str, Observer]=Observer.no_observer_specified) -> List:
    """
    Create and register one or more relations from a single origin to one or more destinations.
    Relation parameters (type and weight) can be specified for each destination, or a default relation class parameter is used
    Relation are assigned to the observer "oer"

    :param state: Registry of all objects
    :param origin: Origin of the relation as string, Processor or Factor
    :param destinations: List of tuples, where each tuple can be of a single element, the string, Processor or Factor, or can be accompanied by the relation parameters, the relation type, and the string specifying the weight
    :param relation_class: Default relation class
    :param oer: str or Observer for the Observer to which relation observations are accounted
    :return: The list of relations
    """
    def get_requested_object(p_, ft_, f_):
        if p_ and not ft_ and not f_:
            return p_
        elif not p_ and ft_ and not f_:
            return ft_
        elif p_ and ft_ and f_:
            return f_

    if isinstance(state, PartialRetrievalDictionary):
        glb_idx = state
    else:
        glb_idx, _, _, _, _ = get_case_study_registry_objects(state)

    # Origin
    p, ft, f = find_or_create_observable(glb_idx, origin)
    initial_origin_obj = get_requested_object(p, ft, f)

    rels = []

    if not oer:
        oer = Observer.no_observer_specified

    if isinstance(oer, str):
        oer_ = glb_idx.get(Observer.partial_key(name=oer))
        if not oer_:
            oer = Observer(oer)
            glb_idx.put(oer.key(), oer)
        else:
            oer = oer_[0]
    elif not isinstance(oer, Observer):
        raise Exception("'oer' parameter must be a string or an Observer instance")

    if not isinstance(destinations, list):
        destinations = [destinations]

    for dst in destinations:
        if not isinstance(dst, tuple):
            dst = tuple([dst])
        origin_obj = initial_origin_obj
        # Destination
        dst_obj = None
        if isinstance(origin_obj, Processor) and relation_class == RelationClassType.pp_part_of:
            # Find dst[0]. If it does not exist, create dest UNDER (hierarchically) origin
            dst_obj = find_observable_by_name(dst[0], glb_idx)
            if not dst_obj:
                name = origin_obj.full_hierarchy_names(glb_idx)[0] + "." + dst[0]
                p, ft, f = find_or_create_observable(glb_idx, name, source=oer)
                dst_obj = get_requested_object(p, ft, f)
                rel = glb_idx.get(ProcessorsRelationPartOfObservation.partial_key(parent=origin_obj, child=dst_obj, observer=oer))
                if rel:
                    rels.append(rel[0])
                continue  # Skip the rest of the loop
            else:
                dst_obj = dst_obj[0]

        if not dst_obj:
            p, ft, f = find_or_create_observable(glb_idx, dst[0])
            dst_obj = get_requested_object(p, ft, f)
            # If origin is Processor and destination is Factor, create Factor in origin (if it does not exist). Or viceversa
            if isinstance(origin_obj, Processor) and isinstance(dst_obj, Factor):
                # Obtain full origin processor name
                names = origin_obj.full_hierarchy_names(glb_idx)
                p, ft, f = find_or_create_observable(glb_idx, names[0] + ":" + dst_obj.taxon.name)
                origin_obj = get_requested_object(p, ft, f)
            elif isinstance(origin_obj, Factor) and isinstance(dst_obj, Processor):
                names = dst_obj.full_hierarchy_names(glb_idx)
                p, ft, f = find_or_create_observable(glb_idx, names[0] + ":" + origin_obj.taxon.name)
                dst_obj = get_requested_object(p, ft, f)
            # Relation class
            if len(dst) > 1:
                rel_type = dst[1]
            else:
                if not relation_class:
                    if isinstance(origin_obj, Processor) and isinstance(dst_obj, Processor):
                        relation_class = RelationClassType.pp_undirected_flow
                    else:
                        relation_class = RelationClassType.ff_directed_flow
                rel_type = relation_class
            if len(dst) > 2:
                weight = dst[2]
            else:
                weight = ""  # No weight, it only can be used to aggregate
            rel = _find_or_create_relation(origin_obj, dst_obj, rel_type, oer, weight, glb_idx)
        rels.append(rel)

    return rels

# ########################################################################################
# Auxiliary functions
# ########################################################################################


def _obtain_name_parts(n):
    """
    Parse the name. List of processor names + list of factor names
    :param n:
    :return:
    """
    r = n.split(":")
    if len(r) > 1:
        full_p_name = r[0]
        full_f_name = r[1]
    else:
        full_p_name = r[0]
        full_f_name = ""
    p_ = full_p_name.split(".")
    f_ = full_f_name.split(".")
    if len(p_) == 1 and not p_[0]:
        p_ = []
    if len(f_) == 1 and not f_[0]:
        f_ = []
    return p_, f_


def _create_quantitative_observation(factor: Factor,
                                     value: str, unit: str,
                                     spread: str, assessment: str, pedigree: str, pedigree_template: str,
                                     observer: Observer,
                                     relative_to: Union[str, Factor],
                                     time: str,
                                     geolocation: str,
                                     comments: str,
                                     tags, other_attributes):
    if other_attributes:
        attrs = other_attributes.copy()
    else:
        attrs = {}
    if relative_to:
        if isinstance(relative_to, str):
            rel2 = relative_to
        else:
            rel2 = relative_to.name
    else:
        rel2 = None
    attrs.update({"relative_to": rel2,
                  "time": time,
                  "geolocation": geolocation,
                  "spread": spread,
                  "assessment": assessment,
                  "pedigree": pedigree,
                  "pedigree_template": pedigree_template,
                  "comments": comments
                  }
                 )

    fo = FactorQuantitativeObservation.create_and_append(v=QualifiedQuantityExpression(value + " " + unit),
                                                         factor=factor,
                                                         observer=observer,
                                                         tags=tags,
                                                         attributes=attrs
                                                         )
    return fo


def _get_observer(observer: Union[str, Observer], idx: PartialRetrievalDictionary) -> Observer:
    res = None
    if isinstance(observer, Observer):
        res = observer
    else:
        oer = idx.get(Observer.partial_key(name=observer))
        if oer:
            res = oer[0]
    return res


def _find_or_create_relation(origin, destination, rel_type: Union[str, RelationClassType], oer: Union[Observer, str], weight: str, state: Union[State, PartialRetrievalDictionary]):
    """
    Construct and register a relation between origin and destination

    :param origin: Either processor or factor
    :param destination: Either processor or factor
    :param rel_type: Relation type. Either a string or a member of RelationClassType enumeration
    :param oer: Observer, as object or string
    :param weight: For flow relations
    :param state: State or PartialRetrievalDictionary
    :return: The relation observation
    """
    # Get objects from state
    if isinstance(state, State):
        glb_idx, _, _, _, _ = get_case_study_registry_objects(state)
    elif isinstance(state, PartialRetrievalDictionary):
        glb_idx = state

    # CREATE the Observer for the relation
    if oer and isinstance(oer, str):
        oer_ = glb_idx.get(Observer.partial_key(name=oer))
        if not oer_:
            oer = Observer(oer)
            glb_idx.put(oer.key(), oer)
        else:
            oer = oer_[0]

    d = {">": RelationClassType.ff_directed_flow,
         "<": RelationClassType.ff_reverse_directed_flow,
         "<>": RelationClassType.pp_undirected_flow,
         "><": RelationClassType.pp_undirected_flow,
         "|": RelationClassType.pp_part_of,
         "||": RelationClassType.pp_upscale
         }
    if isinstance(rel_type, str):
        if rel_type in d:
            rel_type = d[rel_type]

    r = None
    if rel_type == RelationClassType.pp_part_of:
        if isinstance(origin, Processor) and isinstance(destination, Processor):
            # Find or Create the relation
            r = glb_idx.get(ProcessorsRelationPartOfObservation.partial_key(parent=origin, child=destination))
            if not r:
                r = ProcessorsRelationPartOfObservation.create_and_append(origin, destination, oer)  # Part-of
                glb_idx.put(r.key(), r)
            else:
                r = r[0]
            # Add destination to the index with an alternative name
            # TODO Do the same with all part-of children of destination, recursively
            # TODO "full_hierarchy_names" makes use of
            d_name = destination.simple_name()
            for h_name in origin.full_hierarchy_names(glb_idx):
                full_name = h_name+"."+d_name
                p = glb_idx.get(Processor.partial_key(name=full_name))
                if not p:
                    glb_idx.put(Processor.partial_key(name=full_name, ident=destination.ident), destination)
                else:
                    if p[0].ident != destination.ident:
                        raise Exception("Two Processors under name '"+full_name+"' have been found: ID1: "+p[0].ident+"; ID2: "+destination.ident)
    elif rel_type == RelationClassType.pp_undirected_flow:
        if isinstance(origin, Processor) and isinstance(destination, Processor):
            # Find or Create the relation
            r = glb_idx.get(ProcessorsRelationUndirectedFlowObservation.partial_key(source=origin, target=destination))
            if not r:
                r = ProcessorsRelationUndirectedFlowObservation.create_and_append(origin, destination, oer)  # Undirected flow
                glb_idx.put(r.key(), r)
            else:
                r = r[0]
    elif rel_type == RelationClassType.pp_upscale:
        if isinstance(origin, Processor) and isinstance(destination, Processor):
            # Find or Create the relation
            r = glb_idx.get(ProcessorsRelationUpscaleObservation.partial_key(parent=origin, child=destination))
            if not r:
                r = ProcessorsRelationUpscaleObservation.create_and_append(origin, destination, oer, weight)  # Upscale
                glb_idx.put(r.key(), r)
            else:
                r = r[0]
    elif rel_type in (RelationClassType.ff_directed_flow, RelationClassType.ff_reverse_directed_flow):
        if isinstance(origin, Factor) and isinstance(destination, Factor):
            if rel_type == RelationClassType.ff_reverse_directed_flow:
                origin, destination = destination, origin

                if weight:
                    weight = "1/("+weight+")"
            # Find or Create the relation
            r = glb_idx.get(FactorsRelationDirectedFlowObservation.partial_key(source=origin, target=destination))
            if not r:
                r = FactorsRelationDirectedFlowObservation.create_and_append(origin, destination, oer, weight)  # Directed flow
                glb_idx.put(r.key(), r)
            else:
                r = r[0]

    return r


def build_hierarchy(name, type_name, registry: PartialRetrievalDictionary, h: dict, oer: Observer=None, level_names=None):
    """
    Take the result of parsing a hierarchy and elaborate either an Hierarchy (for Categories and FactorType)
    or a set of nested Processors

    Shortcut function

    :param name:
    :param type_name:
    :param registry:
    :param h:
    :param oer: An Observer
    :param level_names:
    :return: If type_name is Processor -> "None". If other, return the Hierarchy object
    """
    if type_name.lower() in ["p"]:
        type_name = "processor"
    elif type_name.lower() in ["f"]:
        type_name = "factortype"
    elif type_name.lower() in ["c", "t"]:
        type_name = "taxon"

    return _build_hierarchy(name, type_name, registry, h, oer, level_names, acum_name="", parent=None)


def _build_hierarchy(name, type_name, registry: PartialRetrievalDictionary, h: dict, oer=None, level_names=None, acum_name="", parent=None):
    """
    Take the result of parsing a hierarchy and elaborate either an Hierarchy (for Categories and FactorType)
    or a set of nested Processors

    :param name: Name of the hierarchy
    :param type_name: Processor, Taxonomy, FactorType
    :param registry: The state, space of variables where the nodes and the hierarchy itself are stored
    :param h: The list of nodes, which can be recursive
    :param oer: The observer of the hierarchy. It is treated differently for Processors, Categories and FactorTypes
    :param level_names:
    :param acum_name: (Internal - do not use) Will contain the acumulated name in hierarchical form
    :param parent: Parent to be used to define the relations in the current level of the hierarchy
    :return:
    """
    # Get or create hierarchy or observer
    if oer:
        hie = oer
    elif name:
        if type_name.lower() == "processor":
            if registry:
                oer = registry.get(Observer.partial_key(name=name))
                if oer:
                    hie = oer[0]
                else:
                    hie = Observer(name)
                    registry.put(hie.key(), hie)
            else:
                hie = Observer(name)
        else:
            if registry:
                hie = registry.get(Hierarchy.partial_key(name=name))
                if not hie:
                    hie = Hierarchy(name, type_name=type_name)
                    registry.put(hie.key(), hie)
                else:
                    hie = hie[0]
            else:
                hie = Hierarchy(name, type_name=type_name)

    for s in h:
        # Create node
        n_name = s["code"]
        if "description" in s:
            desc = s["description"]
        else:
            desc = None
        if "expression" in s:
            exp = s["expression"]
        else:
            exp = None
        if "children" in s:
            children = s["children"]
        else:
            children = []
        # Accumulated name
        acum_name2 = acum_name + ("." if acum_name != "" else "") + n_name

        if type_name.lower() == "processor":
            # Check if the Processor exists
            # If not, create it
            n = registry.get(Processor.partial_key(name=acum_name2))
            if not n:
                attrs = None
                location = None
                proc_external = None
                n = Processor(acum_name2,
                              external=proc_external,
                              location=location,
                              tags=None,
                              attributes=attrs
                              )
                registry.put(n.key(), n)
            else:
                n = n[0]
            if parent:
                # Create "part-of" relation
                rel = _find_or_create_relation(parent, n, RelationClassType.pp_part_of, hie, "", registry)
        elif type_name.lower() == "factortype":
            # Check if the FactorType exists
            # If not, create it
            n = registry.get(FactorType.partial_key(name=acum_name2))
            if not n:
                attrs = None
                fact_roegen_type = FlowFundRoegenType.flow
                n = FactorType(acum_name2,  #
                               parent=parent, hierarchy=hie,
                               tipe=fact_roegen_type,  #
                               tags=None,  # No tags
                               attributes=attrs,
                               expression=exp
                               )
                for alt_name in hierarchical_name_variants(acum_name2):
                    ft_key = FactorType.partial_key(alt_name, n.ident)
                    registry.put(ft_key, n)
            else:
                n = n[0]
        elif type_name.lower() == "taxon":
            # Check if the Taxon exists
            # If not, create it
            n = registry.get(Taxon.partial_key(name=acum_name2))
            if not n:
                n = Taxon(acum_name2, parent=parent, hierarchy=hie, expression=exp)
                for alt_name in hierarchical_name_variants(acum_name2):
                    t_key = Taxon.partial_key(alt_name, n.ident)
                    registry.put(t_key, n)
            else:
                n = n[0]

        if children:
            _build_hierarchy(name, type_name, registry, children, hie, level_names, acum_name2, parent=n)

        # Add node, only for the first level, if it is a hierarchy
        if not parent and isinstance(hie, Hierarchy):
            hie.roots_append(n)

    # Set level names and return the hierarchy, only for the first level, if it is a hierarchy
    if not parent and isinstance(hie, Hierarchy):
        if level_names:
            hie.level_names = level_names

        return hie
    else:
        return None
