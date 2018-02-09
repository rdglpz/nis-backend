import json

from backend.common.helper import create_dictionary
from backend.model_services import IExecutableCommand, State, get_case_study_registry_objects
from backend.command_generators import basic_elements_parser
from backend.model.memory.musiasem_concepts_helper import create_quantitative_observation
from backend.model.memory.musiasem_concepts import FactorType, Observer, FactorInProcessorType, \
    Processor, \
    Factor, FactorQuantitativeObservation, QualifiedQuantityExpression, \
    FlowFundRoegenType, ProcessorsSet, HierarchiesSet, allowed_ff_types


class DataInputCommand(IExecutableCommand):
    """
    Serves to specify quantities (and their qualities) for observables
    If observables (Processor, Factor, FactorInProcessor) do not exist, they are created. This makes this command very powerfu: it may express by itself a MuSIASEM 1.0 structure

    """
    def __init__(self, name: str):
        self._name = name
        self._content = None

    def execute(self, state: "State"):
        """ The execution creates one or more Processors, Factors, FactorInProcessor and Observations
            It also creates "flat" Categories (Code Lists)
            It also Expands referenced Datasets
            Inserting it into "State"
        """
        def process_row(row):
            """
            Process a dictionary representing a row of the data input command. The dictionary can come directly from
            the worksheet or from a dataset.

            Implicitly uses "glb_idx"

            :param row: dictionary
            """
            # From "ff_type" extract: flow/fund, external/internal, incoming/outgoing
            # ecosystem/society?
            ft = row["ff_type"].lower()
            if ft == "int_in_flow":
                roegen_type = FlowFundRoegenType.flow
                internal = True
                incoming = True
            elif ft == "int_in_fund":
                roegen_type = FlowFundRoegenType.fund
                internal = True
                incoming = True
            elif ft == "int_out_flow":
                roegen_type = FlowFundRoegenType.flow
                internal = True
                incoming = False
            elif ft == "ext_in_flow":
                roegen_type = FlowFundRoegenType.flow
                internal = False
                incoming = True
            elif ft == "ext_out_flow":
                roegen_type = FlowFundRoegenType.flow
                internal = False
                incoming = False

            # Split "taxa" attributes. "scale" corresponds to the observation
            p_attributes = row["taxa"].copy()
            if "scale" in p_attributes:
                other_attrs = create_dictionary()
                other_attrs["scale"] = p_attributes["scale"]
                del p_attributes["scale"]
            else:
                other_attrs = None

            # CREATE FactorType (if it does not exist). A Type of Observable
            p, ft, f, o = create_quantitative_observation(
                glb_idx,
                factor=row["processor"]+":"+row["factor"],
                value=row["value"], unit=row["unit"],
                observer=row["source"],
                spread=row["uncertainty"] if "uncertainty" in row else None,
                assessment=row["assessment"] if "assessment" in row else None,
                pedigree=row["pedigree"] if "pedigree" in row else None,
                pedigree_template=row["pedigree_template"] if "pedigree_template" in row else None,
                relative_to=row["relative_to"] if "relative_to" in row else None,
                time=row["time"] if "time" in row else None,
                geolocation=None,
                comments=row["comments"] if "comments" in row else None,
                tags=None,
                other_attributes=other_attrs,
                proc_aliases=None,
                proc_external=False,  # TODO
                proc_attributes=p_attributes,
                proc_location=None,
                ftype_roegen_type=roegen_type,
                ftype_attributes=None,
                fact_external=not internal,
                fact_incoming=incoming,
                fact_location=row["geolocation"] if "geolocation" in row else None
            )
            if p_set.append(p, glb_idx):  # Appends codes to the pset if the processor was not member of the pset
                p_set.append_attributes_codes(row["taxa"])

            # author = state.get("_identity")
            # if not author:
            #     author = "_anonymous"
            #
            # oer = glb_idx.get(Observer.partial_key(author, registry=glb_idx))
            # if not oer:
            #     oer = Observer(author, "Current user" if author != "_anonymous" else "Default anonymous user")
            #     glb_idx.put(oer.key(glb_idx), oer)
            # else:
            #     oer = oer[0]
        # -----------------------------------------------------------------------------------------------------

        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)

        # TODO Check semantic validity, elaborate issues
        issues = []

        p_set_name = self._name.split(" ")[1] if self._name.lower().startswith("processor") else self._name
        if self._name not in p_sets:
            p_set = ProcessorsSet(p_set_name)
            p_sets[p_set_name] = p_set
        else:
            p_set = p_sets[p_set_name]

        # Store code lists (flat "hierarchies")
        for h in self._content["code_lists"]:
            # TODO If some hierarchies already exist, check that they grow (if new codes are added)
            if h not in hh:
                hh[h] = []
            hh[h].extend(self._content["code_lists"][h])

        dataset_column_rule = basic_elements_parser.dataset_with_column

        processor_attributes = self._content["processor_attributes"]

        # Read each of the rows
        for i, r in enumerate(self._content["factor_observations"]):
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
            # If a row contains a reference to a dataset, expand it
            if "_referenced_dataset" in r:
                if r["_referenced_dataset"] in datasets:
                    ds = datasets[r["_referenced_dataset"]]  # Obtain dataset
                else:
                    ds = None
                    issues.append((3, "Dataset '" + r["_referenced_dataset"] + "' is not declared. Row "+str(i)))
            else:
                ds = None
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
        # Directly return the content
        return self._content

    def json_deserialize(self, json_input):
        # TODO Check validity
        issues = []
        if isinstance(json_input, dict):
            self._content = json_input
        else:
            self._content = json.loads(json_input)
        return issues