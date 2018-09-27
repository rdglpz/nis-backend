import json

from backend.command_generators import basic_elements_parser, Issue
from backend.command_generators.basic_elements_parser import dictionary_from_key_value_list
from backend.command_generators.spreadsheet_command_parsers_v2 import IssueLocation
from backend.common.helper import strcmp
from backend.model_services import IExecutableCommand, get_case_study_registry_objects
from backend.models.musiasem_concepts import FlowFundRoegenType, PedigreeMatrix, Reference, ProcessorsSet, FactorType, \
    Processor, Factor, FactorInProcessorType, Observer
from backend.models.musiasem_concepts_helper import create_quantitative_observation, _create_quantitative_observation


class InterfacesAndQualifiedQuantitiesCommand(IExecutableCommand):
    def __init__(self, name: str):
        self._name = name
        self._content = None

    def execute(self, state: "State"):
        def process_row(item):
            """
            Process a dictionary representing a row of the data input command. The dictionary can come directly from
            the worksheet or from a dataset.

            Implicitly uses "glb_idx"

            :param row: dictionary
            """
            # Gather variables
            # Interface
            f_alias = item.get("alias", None)  # Optional, simple_ident
            f_interface_name = item.get("interface", None)  # Optional, simple_ident
            f_interface_type_name = item.get("interface_type", None)  # Optional, simple_ident
            f_processor_name = item.get("processor", None)  # Optional, simple_ident
            f_sphere = item.get("sphere", None)  # Optional, simple_ident
            f_roegen_type = item.get("roegen_type", None)  # Optional, simple_ident
            f_orientation = item.get("orientation", None)  # Optional, simple_ident
            f_opposite_processor_type = item.get("opposite_processor_type", None)
            f_interface_attributes = item.get("interface_attributes", {})  # Optional, simple_ident
            f_location = item.get("location", None)  # Optional, simple_ident

            # Qualified Quantity
            f_value = item.get("value", None)  # Optional, simple_ident
            f_unit = item.get("unit", None)  # Optional, simple_ident
            f_uncertainty = item.get("uncertainty", None)  # Optional, simple_ident
            f_assessment = item.get("assessment", None)  # Optional, simple_ident
            f_pedigree_matrix = item.get("pedigree_matrix", None)  # Optional, simple_ident
            f_pedigree = item.get("pedigree", None)  # Optional, simple_ident
            f_relative_to = item.get("relative_to", None)  # Optional, simple_ident
            f_time = item.get("time", None)  # Optional, simple_ident
            f_source = item.get("qq_source", None)  # Optional, simple_ident
            f_number_attributes = item.get("number_attributes", {})  # Optional, simple_ident
            f_comments = item.get("comments", None)  # Optional, simple_ident

            if f_interface_attributes:
                try:
                    iface_attributes = dictionary_from_key_value_list(f_interface_attributes)
                except Exception as e:
                    issues.append(Issue(itype=3,
                                        description=str(e),
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
            else:
                iface_attributes = {}

            if f_number_attributes:
                try:
                    number_attributes = dictionary_from_key_value_list(f_number_attributes)
                except Exception as e:
                    issues.append(Issue(itype=3,
                                        description=str(e),
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
            else:
                number_attributes = {}

            # Either f_interface_name or both f_processor_name and f_interface_type_name
            if not f_interface_name:
                possibly_local_interface_name = None
                if f_processor_name and f_interface_type_name:
                    f_interface_name = f_processor_name+":"+f_interface_type_name
                else:
                    issues.append(Issue(itype=3,
                                        description="When 'Interface' column is not defined, both 'Processor' and 'InterfaceType' must",
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
            else:
                # TODO Split using syntax analysis. Each of the parts may contain advanced syntactic expressions. For now, only literals are considered
                f_processor_name, f_interface_type_name = f_interface_name.split(":")
                possibly_local_interface_name = f_interface_type_name

            # Check existence of PedigreeMatrix, if used
            if f_pedigree_matrix and f_pedigree:
                pm = glb_idx.get(PedigreeMatrix.partial_key(name=f_pedigree_matrix))
                if len(pm) == 0:
                    issues.append(Issue(itype=3,
                                        description="Could not find Pedigree Matrix '"+f_pedigree_matrix+"'",
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
                else:
                    try:
                        lst = pm[0].get_modes_for_code(f_pedigree)
                    except:
                        issues.append(Issue(itype=3,
                                            description="Could not decode Pedigree '"+f_pedigree+"' for Pedigree Matrix '"+f_pedigree_matrix+"'",
                                            location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                        return
            elif f_pedigree and not f_pedigree_matrix:
                issues.append(Issue(itype=3,
                                    description="Pedigree specified without accompanying Pedigree Matrix",
                                    location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                return

            # Source
            if f_source:
                try:
                    ast = basic_elements_parser.string_to_ast(basic_elements_parser.reference, f_source)
                    ref_id = ast["ref_id"]
                    references = glb_idx.get(Reference.partial_key(ref_id), ref_type="provenance")
                    if len(references) == 1:
                        source = references[0]
                except:
                    # TODO Change when Ref* are implemented
                    source = f_source + " (not found)"
            else:
                source = None

            # Geolocation
            if f_location:
                try:
                    # TODO Change to parser for Location (includes references, but also Codes)
                    ast = basic_elements_parser.string_to_ast(basic_elements_parser.reference, f_location)
                    ref_id = ast["ref_id"]
                    references = glb_idx.get(Reference.partial_key(ref_id), ref_type="geographic")
                    if len(references) == 1:
                        geolocation = references[0]
                except:
                    geolocation = f_location
            else:
                geolocation = None

            # Find Processor
            # TODO Allow creating a basic Processor if it is not found
            p = glb_idx.get(Processor.partial_key(f_processor_name))
            if len(p) == 0:
                issues.append(Issue(itype=3,
                                    description="Processor '"+f_processor_name+"' not declared previously",
                                    location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                return
            elif len(p) > 1:
                issues.append(Issue(itype=3,
                                    description="Processor '"+f_processor_name+"' found "+str(len(p))+" times. It must be uniquely identified.",
                                    location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                return
            else:
                p = p[0]

            f = None
            if possibly_local_interface_name:
                # Find Factor
                p = Processor()
                for ff in p.factors:
                    if strcmp(f.name, possibly_local_interface_name):
                        f = ff
                        ft = f.taxon
                        break
            else:
                ft = None

            if not ft:
                # Find FactorType
                # TODO Allow creating a basic FactorType if it is not found
                ft = glb_idx.get(FactorType.partial_key(f_interface_type_name))
                if len(ft) == 0:
                    issues.append(Issue(itype=3,
                                        description="InterfaceType '"+f_interface_type_name+"' not declared previously",
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
                elif len(ft) > 1:
                    issues.append(Issue(itype=3,
                                        description="InterfaceType '"+f_interface_type_name+"' found "+str(len(ft))+" times. It must be uniquely identified.",
                                        location=IssueLocation(sheet_name=name, row=r + 1, column=None)))
                    return
                else:
                    ft = ft[0]

            if not f:
                # Find or Create Interface
                f = glb_idx.get(Factor.partial_key(processor=p, factor_type=ft))
                if not f:
                    f = Factor.create_and_append(f_interface_type_name,
                                                 p,
                                                 in_processor_type=FactorInProcessorType(
                                                     external=f_opposite_processor_type,
                                                     incoming=f_orientation
                                                 ),
                                                 taxon=ft,
                                                 location=f_location,
                                                 tags=None,
                                                 attributes=iface_attributes)
                    glb_idx.put(f.key(), f)
                else:
                    f = f[0]

            # Find Observer
            oer = glb_idx.get(Observer.partial_key(f_source))
            if not oer:
                # TODO Find reference, and initialize Observer properly!!!
                oer = Observer(f_source)
                glb_idx.put(oer.key(), oer)
            else:
                oer = oer[0]

            # Create quantitative observation
            if f_value:
                o = _create_quantitative_observation(f,
                                                     f_value, f_unit, f_uncertainty, f_assessment, f_pedigree, f_pedigree_matrix,
                                                     oer,
                                                     f_relative_to,
                                                     f_time,
                                                     None,
                                                     f_comments,
                                                     None, number_attributes
                                                     )

                # TODO Register? Disable for now. Observation can be obtained from a pass over all Interfaces
                # glb_idx.put(o.key(), o)

        issues = []
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        name = self._content["command_name"]

        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        
        # TODO ProcessorSet not used. Those must be declared previously
        # p_set_name = self._name.split(" ")[1] if self._name.lower().startswith("processor") else self._name
        # if self._name not in p_sets:
        #     p_set = ProcessorsSet(p_set_name)
        #     p_sets[p_set_name] = p_set
        # else:
        #     p_set = p_sets[p_set_name]

        # TODO Hierarchies not used. They must be declared previously
        # # Store code lists (flat "hierarchies")
        # for h in self._content["code_lists"]:
        #     # TODO If some hierarchies already exist, check that they grow (if new codes are added)
        #     if h not in hh:
        #         hh[h] = []
        #     hh[h].extend(self._content["code_lists"][h])

        dataset_column_rule = basic_elements_parser.dataset_with_column

        #processor_attributes = self._content["processor_attributes"]

        # Read each of the rows
        for i, r in enumerate(self._content["items"]):
            # Create processor, hierarchies (taxa) and factors
            # Check if the processor exists. Two ways to characterize a processor: name or taxa
            """
            ABOUT PROCESSOR NAME
            The processor can have a name and/or a set of qualifications, defining its identity
            If not defined, the name can be assumed to be the qualifications, concatenated
            Is assigning a name for all processors a difficult task? 
            * In the specification moment, it can get in the middle
            * When operating it is not so important
            * If taxa identify uniquely the processor, name is optional, automatically obtained from taxa
            * The benefit is that it can help reducing hierarchic names
            * It may help in readability of the case study

            """
            # Gather variables
            # Interface
            f_alias = r.get("alias", None)  # Optional, simple_ident
            f_interface_name = r.get("interface", None)  # Optional, simple_ident
            f_interface_type_name = r.get("interface_type", None)  # Optional, simple_ident
            f_processor_name = r.get("processor", None)  # Optional, simple_ident
            f_sphere = r.get("sphere", None)  # Optional, simple_ident
            f_roegen_type = r.get("roegen_type", None)  # Optional, simple_ident
            f_orientation = r.get("orientation", None)  # Optional, simple_ident
            f_interface_attributes = r.get("interface_attributes", {})  # Optional, simple_ident
            f_location = r.get("location", None)  # Optional, simple_ident

            # Qualified Quantity
            f_value = r.get("value", None)  # Optional, simple_ident
            f_unit = r.get("unit", None)  # Optional, simple_ident
            f_uncertainty = r.get("uncertainty", None)  # Optional, simple_ident
            f_assessment = r.get("assessment", None)  # Optional, simple_ident
            f_pedigree_matrix = r.get("pedigree_matrix", None)  # Optional, simple_ident
            f_pedigree = r.get("pedigree", None)  # Optional, simple_ident
            f_relative_to = r.get("relative_to", None)  # Optional, simple_ident
            f_time = r.get("time", None)  # Optional, simple_ident
            f_source = r.get("qq_source", None)  # Optional, simple_ident
            f_number_attributes = r.get("number_attributes", {})  # Optional, simple_ident
            f_comments = r.get("comments", None)  # Optional, simple_ident

            # Check if row contains a reference to dataset and/or category hierarchy, or something
            # If a row contains a reference to a dataset, expand it
            # TODO Parse the row. Find referenced Dataset, in case
            ds = None  # type: pd.DataFrame

            if ds:
                # Obtain a dict to map columns to dataset columns
                fixed_dict = {}
                var_dict = {}
                var_taxa_dict = {}
                for k in r:  # Iterate through columns in row "r"
                    if k == "taxa":
                        for t in r[k]:
                            if r[k][t].startswith("#"):
                                var_taxa_dict[t] = r[k][t][1:]
                        fixed_dict["taxa"] = r["taxa"].copy()
                    elif k in ["_referenced_dataset", "_processor_type"]:
                        continue
                    elif not r[k].startswith("#"):
                        fixed_dict[k] = r[k]  # Does not refer to the dataset
                    else:  # Starts with "#"
                        if k != "processor":
                            var_dict[k] = r[k][1:]  # Dimension
                        else:
                            fixed_dict[k] = r[k]  # Special
                # Check that the # names are in the Dataset
                diff = set([v.lower() for v in list(var_dict.values()) + list(var_taxa_dict.values())]).difference(
                    set(ds.data.columns))
                if diff:
                    # There are request fields in var_dict NOT in the input dataset "ds.data"
                    if len(diff) > 1:
                        v = "is"
                    else:
                        v = "are"
                    issues.append((3, "'" + ', '.join(diff) + "' " + v + " not present in the requested dataset '" + r[
                        "_referenced_dataset"] + "'. Columns are: " + ', '.join(ds.data.columns) + ". Row " + str(
                        i + 1)))
                else:
                    # Iterate the dataset (a pd.DataFrame), row by row
                    for r_num, r2 in ds.data.iterrows():
                        r_exp = fixed_dict.copy()
                        r_exp.update({k: str(r2[v.lower()]) for k, v in var_dict.items()})
                        if var_taxa_dict:
                            taxa = r_exp["taxa"]
                            taxa.update({k: r2[v.lower()] for k, v in var_taxa_dict.items()})
                            if r_exp["processor"].startswith("#"):
                                r_exp["processor"] = "_".join([str(taxa[t]) for t in processor_attributes if t in taxa])
                        process_row(r_exp)
            else:  # Literal values
                process_row(r)

        return issues, None

    def estimate_execution_time(self):
        return 0

    def json_serialize(self):
        # Directly return the metadata dictionary
        return self._content

    def json_deserialize(self, json_input):
        # TODO Check validity
        issues = []
        if isinstance(json_input, dict):
            self._content = json_input
        else:
            self._content = json.loads(json_input)

        if "description" in json_input:
            self._description = json_input["description"]
        return issues