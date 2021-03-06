import json
import re

from pint import UndefinedUnitError
from typing import Dict

from backend import ureg, CommandField
from backend.command_executors.execution_helpers import parse_line, classify_variables, \
    obtain_dictionary_with_literal_fields
from backend.command_generators import parser_field_parsers, Issue, IssueLocation, IType
from backend.command_generators.parser_ast_evaluators import dictionary_from_key_value_list, ast_to_string
from backend.common.helper import strcmp, first, ifnull
from backend.model_services import IExecutableCommand, get_case_study_registry_objects
from backend.models.musiasem_concepts import PedigreeMatrix, Reference, FactorType, \
    Processor, Factor, FactorInProcessorType, Observer, Parameter, GeographicReference, ProvenanceReference, \
    BibliographicReference
from backend.models.musiasem_concepts_helper import _create_or_append_quantitative_observation
from backend.solving import get_processor_names_to_processors_dictionary
from backend.command_field_definitions import get_command_fields_from_class


class InterfacesAndQualifiedQuantitiesCommand(IExecutableCommand):
    def __init__(self, name: str):
        self._name = name
        self._content = None

    def execute(self, state: "State"):
        def parse_and_unfold_line(item):
            # Consider multiplicity because of:
            # - A dataset (only one). First a list of dataset concepts used in the line is obtained.
            #   Then the unique tuples formed by them are obtained.
            # - Processor name.
            #   - A set of processors (wildcard or filter by attributes)
            #   - A set of interfaces (according to another filter?)
            # - Multiple types of relation
            # - Both (first each dataset record applied -expanded-, then the name evaluation is applied)
            # - UNRESOLVED: expressions are resolved partially. Parts where parameters
            # expressions depending on parameters. Only the part of the expression depending on varying things
            # - The processor name could be a concatenation of multiple literals
            #
            # Look for multiple items in r_source_processor_name, r_source_interface_name,
            #                            r_target_processor_name, r_target_interface_name
            if item["_complex"]:
                asts = parse_line(item, fields)
                if item["_expandable"]:
                    # It is an expandable line
                    # Look for fields which are specified to be variable in order to originate the expansion
                    res = classify_variables(asts, datasets, hh, parameters)
                    ds_list = res["datasets"]
                    ds_concepts = res["ds_concepts"]
                    h_list = res["hierarchies"]
                    if len(ds_list) >= 1 and len(h_list) >= 1:
                        issues.append(Issue(itype=3,
                                            description="Dataset(s): "+", ".join([d.name for d in ds_list])+", and hierarchy(ies): "+", ".join([h.name for h in h_list])+", have been specified. Only a single dataset is supported.",
                                            location=IssueLocation(sheet_name=name, row=r, column=None)))
                        return
                    elif len(ds_list) > 1:
                        issues.append(Issue(itype=3,
                                            description="More than one dataset has been specified: "+", ".join([d.name for d in ds_list])+", just one dataset is supported.",
                                            location=IssueLocation(sheet_name=name, row=r, column=None)))
                        return
                    elif len(h_list) > 0:
                        issues.append(Issue(itype=3,
                                            description="One or more hierarchies have been specified: " + ", ".join([h.name for h in h_list]),
                                            location=IssueLocation(sheet_name=name, row=r, column=None)))
                        return
                    const_dict = obtain_dictionary_with_literal_fields(item, asts)
                    if len(ds_list) == 1:
                        # If a measure is requested and not all dimensions are used, aggregate or
                        # issue an error (because it is not possible to reduce without aggregation).
                        # If only dimensions are used, then obtain all the unique tuples
                        ds = ds_list[0]
                        measure_requested = False
                        all_dimensions = set([c.code for c in ds.dimensions if not c.is_measure])
                        for con in ds_concepts:
                            for c in ds.dimensions:
                                if strcmp(c.code, con):
                                    if c.is_measure:
                                        measure_requested = True
                                    else:  # Dimension
                                        all_dimensions.remove(c.code)
                        only_dimensions_requested = len(all_dimensions) == 0

                        if measure_requested and not only_dimensions_requested:
                            issues.append(Issue(itype=3,
                                                description="It is not possible to use a measure if not all dataset dimensions are used (cannot assume implicit aggregation)",
                                                location=IssueLocation(sheet_name=name, row=r, column=None)))
                            return
                        elif not measure_requested and not only_dimensions_requested:
                            # TODO Reduce the dataset to the unique tuples (consider the current case -sensitive or not-sensitive-)
                            data = None
                        else:  # Take the dataset as-is!!!
                            data = ds.data

                        # Each row
                        for row in data.iterrows():
                            item2 = const_dict.copy()

                            d = {}
                            for c in ds_concepts:
                                d["{" + ds.code + "." + c + "}"] = row[c]
                            # Expand in all fields
                            for f in fields:
                                if f not in const_dict:
                                    # Replace all
                                    string = item[f]
                                    # TODO Could iterate through the variables in the field (not IN ALL FIELDS of the row)
                                    for item in sorted(d.keys(), key=len, reverse=True):
                                        string = re.sub(item, d[item], string)
                                    item2[f] = string

                            print("Multiple by dataset: " + str(item2))
                            yield item2
                    else:  # No dataset, no hierarchy of categories, but it could be still complex, because of wildcards
                        # For now return just the line
                        yield item
                        # wildcard_in_source = ".." in item.get("source_processor", "")
                        # wildcard_in_target = ".." in item.get("target_processor", "")
                        # if wildcard_in_source or wildcard_in_target:
                        #     r_source_processor_name = string_to_ast(processor_names, item.get("source_processor", None))
                        #     r_target_processor_name = string_to_ast(processor_names, item.get("target_processor", None))
                        #     if wildcard_in_source:
                        #         source_processor_names = obtain_matching_processors(r_source_processor_name, all_processors)
                        #     else:
                        #         source_processor_names = [item["source_processor"]]
                        #     if wildcard_in_target:
                        #         target_processor_names = obtain_matching_processors(r_target_processor_name, all_processors)
                        #     else:
                        #         target_processor_names = [item["target_processor"]]
                        #     for s in source_processor_names:
                        #         for t in target_processor_names:
                        #             item3 = const_dict.copy()
                        #             item3["source_processor"] = s
                        #             item3["target_processor"] = t
                        #             print("Multiple by wildcard: "+str(item3))
                        #             yield item3
                        # else:
                        #     # yield item
                        #     raise Exception("If 'complex' is signaled, it should not pass by this line")
            else:
                # print("Single: "+str(item))
                yield item

        def process_row(item):
            """
            Process a dictionary representing a row of the data input command. The dictionary can come directly from
            the worksheet or from a dataset.

            Implicitly uses "glb_idx"

            :param row: dictionary
            """
            # Gather variables in one dictionary
            fields_value = {k: item.get(k, v.default_value) for k, v in fields.items()}

            # Check if mandatory fields with no value exist
            for field in [k for k, v in fields.items() if v.mandatory and not fields_value[k]]:
                add_issue(IType.error(), f"Mandatory field '{field}' is empty. Skipped.")
                return

            # Interface
            f_alias = fields_value.get("alias")
            f_processor_name = fields_value.get("processor")
            f_interface_type_name = fields_value.get("interface_type")
            f_interface_name = fields_value.get("interface")  # A "simple_ident", optional
            f_location = fields_value.get("location")
            f_orientation = fields_value.get("orientation")
            # f_roegen_type = fields_value.get("roegen_type")
            # f_sphere = fields_value.get("sphere")
            # f_opposite_processor_type = fields_value.get("opposite_processor_type")
            # f_geolocation_ref = fields_value.get("geolocation_ref")
            # f_geolocation_code = fields_value.get("geolocation_code")

            # Qualified Quantity
            f_value = fields_value.get("value")
            f_unit = fields_value.get("unit")
            f_uncertainty = fields_value.get("uncertainty")
            f_assessment = fields_value.get("assessment")
            f_pedigree_matrix = fields_value.get("pedigree_matrix")
            f_pedigree = fields_value.get("pedigree")
            f_relative_to = fields_value.get("relative_to")
            f_time = fields_value.get("time")
            f_source = fields_value.get("qq_source")
            f_number_attributes = fields_value.get("number_attributes", {})
            f_comments = fields_value.get("comments")

            # Transform text of "interface_attributes" into a dictionary
            field_val = fields_value.get("interface_attributes")
            if field_val:
                try:
                    fields_value["interface_attributes"] = dictionary_from_key_value_list(field_val, glb_idx)
                except Exception as e:
                    add_issue(IType.error(), str(e))
                    return
            else:
                fields_value["interface_attributes"] = {}

            # Transform text of "number_attributes" into a dictionary
            if f_number_attributes:
                try:
                    number_attributes = dictionary_from_key_value_list(f_number_attributes, glb_idx)
                except Exception as e:
                    add_issue(IType.error(), str(e))
                    return
            else:
                number_attributes = {}

            # f_processor_name -> p
            # f_interface_type_name -> it
            # f_interface_name -> i
            #
            # IF NOT i AND it AND p => i_name = it.name => get or create "i"
            # IF i AND it AND p => get or create "i", IF "i" exists, i.it MUST BE equal to "it" (IF NOT, error)
            # IF i AND p AND NOT it => get "i" (MUST EXIST)
            if not f_interface_name:
                if not f_interface_type_name:
                    add_issue(IType.error(), "At least one of InterfaceType or Interface must be defined")
                    return

                possibly_local_interface_name = None
                f_interface_name = f_interface_type_name
            else:
                possibly_local_interface_name = f_interface_name

            # Check existence of PedigreeMatrix, if used
            if f_pedigree_matrix and f_pedigree:
                pm = glb_idx.get(PedigreeMatrix.partial_key(name=f_pedigree_matrix))
                if len(pm) == 0:
                    add_issue(IType.error(), "Could not find Pedigree Matrix '" + f_pedigree_matrix + "'")
                    return
                else:
                    try:
                        lst = pm[0].get_modes_for_code(f_pedigree)
                    except:
                        add_issue(IType.error(), "Could not decode Pedigree '" + f_pedigree + "' for Pedigree Matrix '" + f_pedigree_matrix + "'")
                        return
            elif f_pedigree and not f_pedigree_matrix:
                add_issue(IType.error(), "Pedigree specified without accompanying Pedigree Matrix")
                return

            # Source
            if f_source:
                try:
                    ast = parser_field_parsers.string_to_ast(parser_field_parsers.reference, f_source)
                    ref_id = ast["ref_id"]
                    references = glb_idx.get(ProvenanceReference.partial_key(ref_id))
                    if len(references) == 1:
                        source = references[0]
                    else:
                        references = glb_idx.get(BibliographicReference.partial_key(ref_id))
                        if len(references) == 1:
                            source = references[0]
                        else:
                            add_issue(IType.error(), f"Reference '{f_source}' not found")
                except:
                    # TODO Change when Ref* are implemented
                    source = f_source + " (not found)"
            else:
                source = None

            # Geolocation
            if f_location:
                try:
                    # TODO Change to parser for Location (includes references, but also Codes)
                    ast = parser_field_parsers.string_to_ast(parser_field_parsers.reference, f_location)
                    ref_id = ast["ref_id"]
                    references = glb_idx.get(GeographicReference.partial_key(ref_id))
                    if len(references) == 1:
                        geolocation = references[0]
                except:
                    geolocation = f_location
            else:
                geolocation = None

            # Find Processor
            # TODO Allow creating a basic Processor if it is not found?
            p = glb_idx.get(Processor.partial_key(f_processor_name))
            if len(p) == 0:
                add_issue(IType.error(), "Processor '" + f_processor_name + "' not declared previously")
                return
            elif len(p) > 1:
                add_issue(IType.error(), "Processor '" + f_processor_name + "' found " + str(len(p)) + " times. It must be uniquely identified.")
                return
            else:
                p = p[0]

            # Try to find Interface
            ft: FactorType = None
            f = glb_idx.get(Factor.partial_key(processor=p, name=f_interface_name))
            if len(f) == 1:
                f = f[0]
                ft: FactorType = f.taxon
                if f_interface_type_name:
                    if not strcmp(ft.name, f_interface_type_name):
                        add_issue(IType.warning(), f"The InterfaceType of the Interface, {ft.name} "
                                  f"is different from the specified InterfaceType, {f_interface_type_name}. Record skipped.")
                        return
            elif len(f) > 1:
                add_issue(IType.error(), f"Interface '{f_interface_name}' found {str(len(f))} times. "
                                         f"It must be uniquely identified.")
                return
            elif len(f) == 0:
                f: Factor = None  # Does not exist, create it below
                if not f_orientation:
                    add_issue(IType.error(), f"Orientation must be defined for new Interfaces")
                    return

            # InterfaceType still not found
            if not ft:
                # Find FactorType
                # TODO Allow creating a basic FactorType if it is not found
                ft = glb_idx.get(FactorType.partial_key(f_interface_type_name))
                if len(ft) == 0:
                    add_issue(IType.error(), f"InterfaceType '{f_interface_type_name}' not declared previously")
                    return
                elif len(ft) > 1:
                    add_issue(IType.error(), f"InterfaceType '{f_interface_type_name}' found {str(len(ft))} times. "
                                             f"It must be uniquely identified.")
                    return
                else:
                    ft = ft[0]

            if not f:
                # Get attributes default values taken from Interface Type or Processor attributes
                default_values = {
                    # "orientation": ft.orientation,
                    "sphere": ft.sphere,
                    "roegen_type": ft.roegen_type,
                    "opposite_processor_type": p.subsystem_type
                }

                # Get internal and user-defined attributes in one dictionary
                attributes = {k: ifnull(fields_value[k], default_values.get(k, None))
                              for k, v in fields.items() if v.attribute_of == Factor}
                attributes.update(fields_value["interface_attributes"])

                f = Factor.create_and_append(f_interface_name,
                                             p,
                                             in_processor_type=FactorInProcessorType(
                                                 external=False,
                                                 incoming=False
                                             ),
                                             taxon=ft,
                                             geolocation=f_location,
                                             tags=None,
                                             attributes=attributes)
                glb_idx.put(f.key(), f)

            # Find Observer
            oer = glb_idx.get(Observer.partial_key(f_source))
            if not oer:
                add_issue(IType.warning(), f"Observer '{f_source}' has not been found.")
            else:
                oer = oer[0]

            if f_relative_to:
                ast = parser_field_parsers.string_to_ast(parser_field_parsers.factor_unit, f_relative_to)
                relative_to_interface_name = ast_to_string(ast["factor"])

                rel_unit_name = ast["unparsed_unit"]
                try:
                    f_unit = str((ureg(f_unit) / ureg(rel_unit_name)).units)
                except (UndefinedUnitError, AttributeError) as ex:
                    add_issue(3, f"The final unit could not be computed, interface '{f_unit}' / "
                                 f"relative_to '{rel_unit_name}': {str(ex)}")
                    return

                f_relative_to = first(f.processor.factors, lambda ifc: strcmp(ifc.name, relative_to_interface_name))

                if not f_relative_to:
                    add_issue(IType.error(), f"Interface specified in 'relative_to' column "
                                             f"'{relative_to_interface_name}' has not been found.")
                    return

            # Create quantitative observation
            if f_value:
                # If an observation exists then "time" is mandatory
                if not f_time:
                    add_issue(IType.error(), f"Field 'time' needs to be specified for the given observation.")
                    return

                o = _create_or_append_quantitative_observation(f,
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

        def add_issue(itype: int, description: str):
            issues.append(
                Issue(itype=itype,
                      description=description,
                      location=IssueLocation(sheet_name=name,
                                             row=i, column=None))
            )
            return

        issues = []
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)
        name = self._content["command_name"]

        # CommandField definitions for the fields of Interface command
        fields: Dict[str, CommandField] = {f.name: f for f in get_command_fields_from_class(self.__class__)}
        # Obtain the names of all parameters
        parameters = [p.name for p in glb_idx.get(Parameter.partial_key())]
        # Obtain the names of all processors
        all_processors = get_processor_names_to_processors_dictionary(glb_idx)

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

        dataset_column_rule = parser_field_parsers.dataset_with_column

        #processor_attributes = self._content["processor_attributes"]

        # Read each of the rows
        for r in self._content["items"]:
            i = r["_row"]
            for sub_line in parse_and_unfold_line(r):
                process_row(sub_line)

            # # Create processor, hierarchies (taxa) and factors
            # # Check if the processor exists. Two ways to characterize a processor: name or taxa
            # """
            # ABOUT PROCESSOR NAME
            # The processor can have a name and/or a set of qualifications, defining its identity
            # If not defined, the name can be assumed to be the qualifications, concatenated
            # Is assigning a name for all processors a difficult task?
            # * In the specification moment, it can get in the middle
            # * When operating it is not so important
            # * If taxa identify uniquely the processor, name is optional, automatically obtained from taxa
            # * The benefit is that it can help reducing hierarchic names
            # * It may help in readability of the case study
            #
            # """
            # # Gather variables
            # # Interface
            # f_alias = r.get("alias", None)
            # f_interface_name = r.get("interface", None)
            # f_interface_type_name = r.get("interface_type", None)
            # f_processor_name = r.get("processor", None)
            # f_sphere = r.get("sphere", None)
            # f_roegen_type = r.get("roegen_type", None)
            # f_orientation = r.get("orientation", None)
            # f_interface_attributes = r.get("interface_attributes", {})
            # f_location = r.get("location", None)
            #
            # # Qualified Quantity
            # f_value = r.get("value", None)
            # f_unit = r.get("unit", None)
            # f_uncertainty = r.get("uncertainty", None)
            # f_assessment = r.get("assessment", None)
            # f_pedigree_matrix = r.get("pedigree_matrix", None)
            # f_pedigree = r.get("pedigree", None)
            # f_relative_to = r.get("relative_to", None)
            # f_time = r.get("time", None)
            # f_source = r.get("qq_source", None)
            # f_number_attributes = r.get("number_attributes", {})
            # f_comments = r.get("comments", None)
            #
            # # Check if row contains a reference to dataset and/or category hierarchy, or something
            # # If a row contains a reference to a dataset, expand it
            # # TODO Parse the row. Find referenced Dataset, in case
            # ds = None  # type: pd.DataFrame
            #
            # if ds:
            #     # Obtain a dict to map columns to dataset columns
            #     fixed_dict = {}
            #     var_dict = {}
            #     var_taxa_dict = {}
            #     for k in r:  # Iterate through columns in row "r"
            #         if k == "taxa":
            #             for t in r[k]:
            #                 if r[k][t].startswith("#"):
            #                     var_taxa_dict[t] = r[k][t][1:]
            #             fixed_dict["taxa"] = r["taxa"].copy()
            #         elif k in ["_referenced_dataset", "_processor_type"]:
            #             continue
            #         elif not r[k].startswith("#"):
            #             fixed_dict[k] = r[k]  # Does not refer to the dataset
            #         else:  # Starts with "#"
            #             if k != "processor":
            #                 var_dict[k] = r[k][1:]  # Dimension
            #             else:
            #                 fixed_dict[k] = r[k]  # Special
            #     # Check that the # names are in the Dataset
            #     diff = set([v.lower() for v in list(var_dict.values()) + list(var_taxa_dict.values())]).difference(
            #         set(ds.data.columns))
            #     if diff:
            #         # There are request fields in var_dict NOT in the input dataset "ds.data"
            #         if len(diff) > 1:
            #             v = "is"
            #         else:
            #             v = "are"
            #         issues.append((3, "'" + ', '.join(diff) + "' " + v + " not present in the requested dataset '" + r[
            #             "_referenced_dataset"] + "'. Columns are: " + ', '.join(ds.data.columns) + ". Row " + str(
            #             i + 1)))
            #     else:
            #         # Iterate the dataset (a pd.DataFrame), row by row
            #         for r_num, r2 in ds.data.iterrows():
            #             r_exp = fixed_dict.copy()
            #             r_exp.update({k: str(r2[v.lower()]) for k, v in var_dict.items()})
            #             if var_taxa_dict:
            #                 taxa = r_exp["taxa"]
            #                 taxa.update({k: r2[v.lower()] for k, v in var_taxa_dict.items()})
            #                 if r_exp["processor"].startswith("#"):
            #                     r_exp["processor"] = "_".join([str(taxa[t]) for t in processor_attributes if t in taxa])
            #             process_row(r_exp)
            # else:  # Literal values
            #     process_row(r)

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