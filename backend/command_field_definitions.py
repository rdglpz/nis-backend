######################################
#  LIST OF FIELDS FOR THE COMMANDS   #
######################################

from typing import Dict, List, Type

from backend import CommandField
from backend.command_generators.parser_field_parsers import simple_ident, unquoted_string, alphanums_string, \
    hierarchy_expression_v2, key_value_list, key_value, expression_with_parameters, \
    time_expression, indicator_expression, code_string, simple_h_name, domain_definition, unit_name, url_parser, \
    processor_names, value, list_simple_ident, reference, processor_name
from backend.models.musiasem_concepts import Processor, Factor
from backend.command_definitions import valid_v2_command_names, commands
from backend.common.helper import first, class_full_name
from backend.model_services import IExecutableCommand

data_types = ["Number", "Boolean", "URL", "UUID", "Datetime", "String", "UnitName", "Code", "Geo"]
concept_types = ["Dimension", "Measure", "Attribute"]
parameter_types = ["Number", "Code", "Boolean", "String"]
element_types = ["Parameter", "Processor", "InterfaceType", "Interface"]
spheres = ["Biosphere", "Technosphere"]
roegen_types = ["Flow", "Fund"]
orientations = ["Input", "Output"]
no_yes = ["No", "Yes"]
yes_no = ["Yes", "No"]
processor_types = ["Local", "Environment", "External", "ExternalEnvironment"]
functional_or_structural = ["Functional", "Structural"]
instance_or_archetype = ["Instance", "Archetype"]
copy_interfaces_mode = ["No", "FromParent", "FromChildren", "Bidirectional"]
source_cardinalities = ["One", "Zero", "ZeroOrOne", "ZeroOrMore", "OneOrMore"]
target_cardinalities = source_cardinalities
relation_types = [# Relationships between Processors
                  "is_a", "IsA",  # "Left" gets a copy of ALL "Right" interface types
                  "as_a", "AsA",  # Left must already have ALL interfaces from Right. Similar to "part-of" in the sense that ALL Right interfaces are connected from Left to Right
                  "part_of", "|", "PartOf",  # The same thing. Left is inside Right. No assumptions on flows between child and parent.
                  "aggregate", "aggregation",
                  "compose",
                  "associate", "association",
                  # Relationships between interfaces
                  "flow", "scale", ">", "<"
                  ]
processor_scaling_types = ["CloneAndScale", "Scale", "CloneScaled"]
agent_types = ["Person", "Software", "Organization"]
geographic_resource_types = ["dataset"]
geographic_topic_categories = ["Farming", "Biota", "Boundaries", "Climatology", "Meteorology", "Atmosphere", "Economy", "Elevation", "Environment", "GeoscientificInformation", "Health", "Imagery", "BaseMaps", "EarthCover", "Intelligence", "Military", "InlandWaters", "Location", "Oceans", "Planning", "Cadastre", "Society", "Structure", "Transportation", "Utilities", "Communication"]
bib_entry_types = ["article", "book", "booklet", "conference", "inbook", "incollection", "inproceedings",
                   "manual", "mastersthesis", "misc", "phdtesis", "proceedings", "techreport", "unpublished"]
bib_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

attributeRegex = "@.+"


# Version 2 only
command_fields: Dict[str, List[CommandField]] = {
        
    "cat_hierarchies": [
        CommandField(allowed_names=["Source"], name="source", parser=simple_h_name),
        CommandField(allowed_names=["HierarchyGroup"], name="hierarchy_group", parser=simple_ident),
        CommandField(allowed_names=["Hierarchy", "HierarchyName"], name="hierarchy_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Level", "LevelCode"], name="level", parser=alphanums_string),
        CommandField(allowed_names=["ReferredHierarchy"], name="referred_hierarchy", parser=simple_h_name),
        CommandField(allowed_names=["Code"], name="code", parser=code_string),
        # NOTE: Removed because parent code must be already a member of the hierarchy being defined
        # CommandField(allowed_names=["ReferredHierarchyParent"], name="referred_hierarchy_parent", parser=simple_ident),
        CommandField(allowed_names=["ParentCode"], name="parent_code", parser=code_string),
        CommandField(allowed_names=["Label"], name="label", parser=unquoted_string),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string),
        CommandField(allowed_names=["Expression", "Formula"], name="expression", parser=hierarchy_expression_v2),
        CommandField(allowed_names=["GeolocationRef"], name="geolocation_ref", parser=reference),
        CommandField(allowed_names=["GeolocationCode"], name="geolocation_code", parser=code_string),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list),
        CommandField(allowed_names=[attributeRegex], name="attributes", many_appearances=True, parser=value)
    ],
    
    "cat_hier_mapping": [
        CommandField(allowed_names=["OriginDataset"], name="source_dataset", parser=simple_h_name),
        CommandField(allowed_names=["OriginHierarchy"], name="source_hierarchy", mandatory=True, parser=simple_h_name),
        CommandField(allowed_names=["OriginCode"], name="source_code", mandatory=True, parser=code_string),
        CommandField(allowed_names=["DestinationHierarchy"], name="destination_hierarchy", mandatory=True, parser=simple_h_name),
        CommandField(allowed_names=["DestinationCode"], name="destination_code", mandatory=True, parser=code_string),
        CommandField(allowed_names=["Weight"], name="weight", mandatory=True, parser=expression_with_parameters),
    ],

    "attribute_types": [
        CommandField(allowed_names=["AttributeType", "AttributeTypeName"], name="attribute_type_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Type"], name="data_type", mandatory=True, allowed_values=data_types, parser=simple_ident),
        CommandField(allowed_names=["ElementTypes"], name="element_types", allowed_values=element_types, parser=list_simple_ident),
        CommandField(allowed_names=["Domain"], name="domain", parser=domain_definition)  # "domain_definition" for Category and NUmber. Boolean is only True or False. Other data types cannot be easily constrained (URL, UUID, Datetime, Geo, String)
    ],

    "datasetdef": [
        CommandField(allowed_names=["Dataset", "DatasetName"], name="dataset_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["DatasetDataLocation"], name="dataset_data_location", mandatory=True, parser=url_parser),
        CommandField(allowed_names=["ConceptType"], name="concept_type", mandatory=True, allowed_values=concept_types, parser=simple_ident),
        CommandField(allowed_names=["Concept", "ConceptName"], name="concept_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["DataType", "ConceptDataType"], name="concept_data_type", mandatory=True, allowed_values=data_types, parser=simple_ident),
        CommandField(allowed_names=["Domain", "ConceptDomain"], name="concept_domain", parser=domain_definition),
        CommandField(allowed_names=["Description", "ConceptDescription"], name="concept_description", parser=unquoted_string),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list)
    ],

    "attribute_sets": [
        CommandField(allowed_names=["AttributeSetName"], name="attribute_set_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list),
        CommandField(allowed_names=[attributeRegex], name="attributes", many_appearances=True, parser=value)
    ],

    "parameters": [
        CommandField(allowed_names=["Parameter", "ParameterName"], name="name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Type"], name="type", mandatory=True, allowed_values=parameter_types, parser=simple_ident),
        CommandField(allowed_names=["Domain"], name="domain", parser=domain_definition),
        CommandField(allowed_names=["Value"], name="value", parser=expression_with_parameters),
        CommandField(allowed_names=["Group"], name="group", parser=simple_ident),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list),
        CommandField(allowed_names=[attributeRegex], name="attributes", many_appearances=True, parser=value)
    ],

    "interface_types": [
        CommandField(allowed_names=["InterfaceTypeHierarchy"], name="interface_type_hierarchy", parser=simple_ident),
        CommandField(allowed_names=["InterfaceType"], name="interface_type", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Sphere"], name="sphere", mandatory=True, allowed_values=spheres,
                     parser=simple_ident),
        CommandField(allowed_names=["RoegenType"], name="roegen_type", mandatory=True, allowed_values=roegen_types,
                     parser=simple_ident),
        CommandField(allowed_names=["ParentInterfaceType"], name="parent_interface_type", parser=simple_ident),
        CommandField(allowed_names=["Formula", "Expression"], name="formula", parser=unquoted_string),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string),
        CommandField(allowed_names=["Unit"], name="unit", parser=unit_name),
        CommandField(allowed_names=["OppositeProcessorType"], name="opposite_processor_type",
                     allowed_values=processor_types, parser=simple_ident, attribute_of=Factor),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list),
        CommandField(allowed_names=[attributeRegex], name="attributes", many_appearances=True, parser=value)
    ],

    "processors": [
        CommandField(allowed_names=["ProcessorGroup"], name="processor_group", parser=simple_ident),
        CommandField(allowed_names=["Processor"], name="processor", mandatory=True, parser=processor_name),
        CommandField(allowed_names=["ParentProcessor"], name="parent_processor", parser=processor_name),
        CommandField(allowed_names=["CopyInterfaces"], name="copy_interfaces_mode",
                     default_value=copy_interfaces_mode[0], allowed_values=copy_interfaces_mode, parser=simple_ident),
        CommandField(allowed_names=["CloneProcessor"], name="clone_processor", parser=simple_ident),
        CommandField(allowed_names=["SubsystemType", "ProcessorContextType", "ProcessorType"], name="subsystem_type",
                     default_value=processor_types[0], allowed_values=processor_types, parser=simple_ident,
                     attribute_of=Processor),
        CommandField(allowed_names=["System"], name="processor_system", default_value="_default_system",
                     parser=simple_ident, attribute_of=Processor),
        CommandField(allowed_names=["FunctionalOrStructural"], name="functional_or_structural",
                     default_value=functional_or_structural[0], allowed_values=functional_or_structural,
                     parser=simple_ident, attribute_of=Processor),
        CommandField(allowed_names=["InstanceOrArchetype"], name="instance_or_archetype",
                     default_value=instance_or_archetype[0], allowed_values=instance_or_archetype, parser=simple_ident,
                     attribute_of=Processor),
        CommandField(allowed_names=["Stock"], name="stock", default_value=no_yes[0], allowed_values=no_yes,
                     parser=simple_ident, attribute_of=Processor),
        CommandField(allowed_names=["Alias", "SpecificName"], name="alias", parser=simple_ident),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string),
        CommandField(allowed_names=["GeolocationRef"], name="geolocation_ref", parser=reference),
        CommandField(allowed_names=["GeolocationCode"], name="geolocation_code", parser=code_string),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list),
        CommandField(allowed_names=[attributeRegex], name="attributes", many_appearances=True, parser=value)
    ],

    "interfaces_and_qq": [
        CommandField(allowed_names=["Processor"], name="processor", mandatory=True, parser=processor_name),
        CommandField(allowed_names=["InterfaceType"], name="interface_type", parser=simple_ident),
        CommandField(allowed_names=["Interface"], name="interface", parser=simple_ident),
        CommandField(allowed_names=["Sphere"], name="sphere", allowed_values=spheres, parser=simple_ident,
                     attribute_of=Factor),
        CommandField(allowed_names=["RoegenType"], name="roegen_type", allowed_values=roegen_types, parser=simple_ident,
                     attribute_of=Factor),
        CommandField(allowed_names=["Orientation"], name="orientation", allowed_values=orientations,
                     parser=simple_ident, attribute_of=Factor),
        CommandField(allowed_names=["OppositeProcessorType"], name="opposite_processor_type",
                     allowed_values=processor_types, parser=simple_ident, attribute_of=Factor),
        CommandField(allowed_names=["GeolocationRef"], name="geolocation_ref", parser=reference),
        CommandField(allowed_names=["GeolocationCode"], name="geolocation_code", parser=code_string),
        CommandField(allowed_names=["Alias", "SpecificName"], name="alias", parser=simple_ident),
        CommandField(allowed_names=["InterfaceAttributes"], name="interface_attributes", parser=key_value_list),
        CommandField(allowed_names=["I"+attributeRegex], name="interface_attributes", many_appearances=True,
                     parser=value),
        # Qualified Quantification
        CommandField(allowed_names=["Value"], name="value", parser=expression_with_parameters),
        CommandField(allowed_names=["Unit"], name="unit", parser=unit_name),
        CommandField(allowed_names=["Uncertainty"], name="uncertainty", parser=unquoted_string),
        CommandField(allowed_names=["Assessment"], name="assessment", parser=unquoted_string),
        # TODO
        #CommandField(allowed_names=["PedigreeMatrix"], name="pedigree_matrix", parser=reference_name),
        #CommandField(allowed_names=["Pedigree"], name="pedigree", parser=pedigree_code),
        #CommandField(allowed_names=["RelativeTo"], name="relative_to", parser=simple_ident_plus_unit_name),
        CommandField(allowed_names=["PedigreeMatrix"], name="pedigree_matrix", parser=reference),
        CommandField(allowed_names=["Pedigree"], name="pedigree", parser=unquoted_string),
        CommandField(allowed_names=["RelativeTo"], name="relative_to", parser=unquoted_string),
        CommandField(allowed_names=["Time"], name="time", parser=time_expression),
        CommandField(allowed_names=["Source"], name="qq_source", parser=reference),
        CommandField(allowed_names=["NumberAttributes"], name="number_attributes", parser=key_value_list),
        CommandField(allowed_names=["N"+attributeRegex], name="number_attributes", many_appearances=True,
                     parser=key_value),
        CommandField(allowed_names=["Comments"], name="comments", parser=unquoted_string)
    ],

    "relationships": [
        CommandField(allowed_names=["OriginProcessors", "OriginProcessor"], name="source_processor", parser=processor_names),
        CommandField(allowed_names=["OriginInterface"], name="source_interface", parser=simple_ident),
        CommandField(allowed_names=["DestinationProcessors", "DestinationProcessor"], name="target_processor", parser=processor_names),
        CommandField(allowed_names=["DestinationInterface"], name="target_interface", parser=simple_ident),
        CommandField(allowed_names=["Origin"], name="source", parser=simple_ident),
        CommandField(allowed_names=["Destination"], name="target", parser=simple_ident),
        CommandField(allowed_names=["RelationType"], name="relation_type", mandatory=True, allowed_values=relation_types, parser=unquoted_string),
        CommandField(allowed_names=["ChangeOfTypeScale"], name="change_type_scale", parser=expression_with_parameters),
        CommandField(allowed_names=["Weight"], name="flow_weight", parser=expression_with_parameters),
        CommandField(allowed_names=["OriginCardinality"], name="source_cardinality", allowed_values=source_cardinalities, parser=simple_ident),
        CommandField(allowed_names=["DestinationCardinality"], name="target_cardinality", allowed_values=target_cardinalities, parser=simple_ident),
        CommandField(allowed_names=["Attributes"], name="attributes", parser=key_value_list)
    ],

    "processor_scalings": [
        CommandField(allowed_names=["InvokingProcessor"], name="invoking_processor", mandatory=True, parser=processor_name),
        CommandField(allowed_names=["RequestedProcessor"], name="requested_processor", mandatory=True, parser=processor_name),
        CommandField(allowed_names=["ScalingType"], name="scaling_type", mandatory=True, allowed_values=processor_scaling_types, parser=simple_ident),
        CommandField(allowed_names=["InvokingInterface"], name="invoking_interface", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["RequestedInterface"], name="requested_interface", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["NewProcessorName"], name="new_processor_name", allowed_values=None, parser=processor_name),
        CommandField(allowed_names=["Scale"], name="scale", mandatory=True, parser=expression_with_parameters)
        # TODO Add other BareProcessor fields
        #CommandField(allowed_names=["UpscaleParentContext"], name="upscale_parent_context", parser=upscale_context),
        #CommandField(allowed_names=["UpscaleChildContext"], name="upscale_child_context", parser=upscale_context)
    ],

    "scale_conversion_v2": [
        CommandField(allowed_names=["OriginHierarchy"], name="source_hierarchy", parser=simple_ident),
        CommandField(allowed_names=["OriginInterfaceType"], name="source_interface_type", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["DestinationHierarchy"], name="target_hierarchy", parser=simple_ident),
        CommandField(allowed_names=["DestinationInterfaceType"], name="target_interface_type", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["OriginContext"], name="source_context", parser=processor_names),
        CommandField(allowed_names=["DestinationContext"], name="target_context", parser=processor_names),
        CommandField(allowed_names=["Scale"], name="scale", parser=expression_with_parameters),
        CommandField(allowed_names=["OriginUnit"], name="source_unit", parser=unit_name),
        CommandField(allowed_names=["DestinationUnit"], name="target_unit", parser=unit_name)
    ],

    "import_commands": [
        CommandField(allowed_names=["Workbook", "WorkbookLocation"], name="workbook_name", parser=url_parser),
        CommandField(allowed_names=["Worksheets"], name="worksheets", parser=unquoted_string)
    ],

    "list_of_commands": [
        CommandField(allowed_names=["Worksheet", "WorksheetName"], name="worksheet", mandatory=True, parser=unquoted_string),
        CommandField(allowed_names=["Command"], name="command", mandatory=True, allowed_values=valid_v2_command_names, parser=simple_ident),
        CommandField(allowed_names=["Comment", "Description"], name="comment", parser=unquoted_string)
    ],

    "ref_provenance": [
        # Reduced, from W3C Provenance Recommendation
        CommandField(allowed_names=["RefID", "Reference"], name="ref_id", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["AgentType"], name="agent_type", mandatory=True, allowed_values=agent_types, parser=simple_ident),
        CommandField(allowed_names=["Agent"], name="agent", mandatory=True, parser=unquoted_string),
        CommandField(allowed_names=["Activities"], name="activities", mandatory=True, parser=unquoted_string),
        CommandField(allowed_names=["Entities"], name="entities", parser=unquoted_string)
    ],

    "ref_geographical": [
        # A subset of fields from INSPIRE regulation for metadata: https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32008R1205&from=EN
        # Fields useful to elaborate graphical displays. Augment in the future as demanded
        CommandField(allowed_names=["RefID", "Reference"], name="ref_id", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Title"], name="title", mandatory=True, parser=unquoted_string),
        CommandField(allowed_names=["Abstract"], name="abstract", parser=unquoted_string),  # Syntax??
        CommandField(allowed_names=["Type"], name="type", allowed_values=geographic_resource_types, parser=unquoted_string),  # Part D.1. JUST "Dataset"
        CommandField(allowed_names=["ResourceLocator", "DataLocation"], name="data_location", parser=url_parser),
        CommandField(allowed_names=["TopicCategory"], name="topic_category", allowed_values=geographic_topic_categories, parser=unquoted_string),  # Part D.2
        CommandField(allowed_names=["BoundingBox"], name="bounding_box", parser=unquoted_string),  # Syntax??
        CommandField(allowed_names=["TemporalExtent", "Date"], name="temporal_extent", parser=unquoted_string),  # Syntax??
        CommandField(allowed_names=["PointOfContact"], name="metadata_point_of_contact", parser=unquoted_string)
    ],

    "ref_bibliographic": [
        # From BibTex. Mandatory fields depending on EntryType, at "https://en.wikipedia.org/wiki/BibTeX" (or search: "Bibtex entry field types")
        CommandField(allowed_names=["RefID", "Reference"], name="ref_id", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["EntryType"], name="entry_type", mandatory=True, allowed_values=bib_entry_types, parser=unquoted_string),
        CommandField(allowed_names=["Address"], name="address", parser=unquoted_string),
        CommandField(allowed_names=["Annote"], name="annote", parser=unquoted_string),
        CommandField(allowed_names=["Author"], name="author", mandatory="entry_type not in ('booklet', 'manual', 'misc', 'proceedings')", parser=unquoted_string),
        CommandField(allowed_names=["BookTitle"], name="booktitle", mandatory="entry_type in ('incollection', 'inproceedings')", parser=unquoted_string),
        CommandField(allowed_names=["Chapter"], name="chapter", mandatory="entry_type in ('inbook')", parser=unquoted_string),
        CommandField(allowed_names=["CrossRef"], name="crossref", parser=unquoted_string),
        CommandField(allowed_names=["Edition"], name="edition", parser=unquoted_string),
        CommandField(allowed_names=["Editor"], name="editor", mandatory="entry_type in ('book', 'inbook')", parser=unquoted_string),
        CommandField(allowed_names=["HowPublished"], name="how_published", parser=unquoted_string),
        CommandField(allowed_names=["Institution"], name="institution", mandatory="entry_type in ('techreport')", parser=unquoted_string),
        CommandField(allowed_names=["Journal"], name="journal", mandatory="entry_type in ('article')", parser=unquoted_string),
        CommandField(allowed_names=["Key"], name="key", parser=unquoted_string),
        CommandField(allowed_names=["Month"], name="month", allowed_values=bib_months, parser=simple_ident),
        CommandField(allowed_names=["Note"], name="note", parser=unquoted_string),
        CommandField(allowed_names=["Number"], name="number", parser=unquoted_string),
        CommandField(allowed_names=["Organization"], name="organization", parser=unquoted_string),
        CommandField(allowed_names=["Pages"], name="pages", mandatory="entry_type in ('inbook')", parser=unquoted_string),
        CommandField(allowed_names=["Publisher"], name="publisher", mandatory="entry_type in ('book', 'inbook', 'incollection')", parser=unquoted_string),
        CommandField(allowed_names=["School"], name="school", mandatory="entry_type in ('mastersthesis', 'phdtesis')", parser=unquoted_string),
        CommandField(allowed_names=["Series"], name="series", parser=unquoted_string),
        CommandField(allowed_names=["Title"], name="title", mandatory="entry_type not in ('misc')", parser=unquoted_string),
        CommandField(allowed_names=["Type"], name="type", parser=unquoted_string),
        CommandField(allowed_names=["URL"], name="url", parser=url_parser),
        CommandField(allowed_names=["Volume"], name="volume", mandatory="entry_type in ('article')", parser=unquoted_string),
        CommandField(allowed_names=["Year"], name="year", mandatory="entry_type in ('article', 'book', 'inbook', 'incollection', 'inproceedings', 'mastersthesis', 'phdthesis', 'proceedings', 'techreport')", parser=unquoted_string)
    ],

    "scalar_indicators": [
        CommandField(allowed_names=["Indicator"], name="indicator_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Local"], name="local", mandatory=True, allowed_values=yes_no, parser=simple_ident),
        CommandField(allowed_names=["Formula", "Expression"], name="expression", mandatory=True, parser=indicator_expression),
        CommandField(allowed_names=["Benchmark"], name="benchmark", parser=simple_ident),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string)
    ],

    "matrix_indicators": [
        CommandField(allowed_names=["Indicator"], name="indicator_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Formula", "Expression"], name="expression", mandatory=True, parser=indicator_expression),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string)
    ],

    "problem_statement": [
        CommandField(allowed_names=["Scenario"], name="scenario_name", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Parameter"], name="parameter", mandatory=True, parser=simple_ident),
        CommandField(allowed_names=["Value"], name="parameter_value", mandatory=True, parser=expression_with_parameters),
        CommandField(allowed_names=["Description"], name="description", parser=unquoted_string)
    ]
}


def get_command_fields_from_class(execution_class: Type[IExecutableCommand]) -> List[CommandField]:
    execution_class_name: str = class_full_name(execution_class)
    cmd = first(commands, condition=lambda c: c.execution_class_name == execution_class_name)
    if cmd:
        return command_fields.get(cmd.name, [])

    return []


# command_field_names = {}
# for fields in command_fields.values():
#     for field in fields:
#         for name in field.allowed_names:
#             command_field_names[name] = field.name
_command_field_names = {name: f.name for fields in command_fields.values() for f in fields for name in f.allowed_names}
print(f'command_field_names = {_command_field_names}')
