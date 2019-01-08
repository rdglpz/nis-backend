import importlib
import regex as re
from typing import Optional, Any, List, Tuple, Callable, Dict

import pint
from collections import namedtuple
from attr import attrs, attrib

# GLOBAL VARIABLES

engine = None

# Database containing OLAP data (cache of Data Cubes)
data_engine = None

# Data source manager
data_source_manager = None  # type: DataSourceManager

# REDIS
redis = None

# Case sensitive
case_sensitive = False

# Create units registry
ureg = pint.UnitRegistry()
ureg.define("cubic_meter = m^3 = m3")
ureg.define("euro = [] = EUR = Eur = eur = Euro = Euros = €")
ureg.define("dollar = [] = USD = Usd = usd = Dollar = Dollars = $")

# Named tuples
Issue = namedtuple("Issue",
                   "sheet_number sheet_name c_type type message")  # (Sheet #, Sheet name, command type, issue type, message)

SDMXConcept = namedtuple('Concept', 'type name istime description code_list')

# Global Types

IssuesOutputPairType = Tuple[Optional[List[Issue]], Optional[Any]]
CommandIssuesPairType = Tuple[Optional["IExecutableCommand"], List[Issue]]
IssuesLabelContentTripleType = Tuple[List[Issue], Optional[Any], Optional[Dict[str, Any]]]
# Tuple (top, bottom, left, right) representing the rectangular area of the input worksheet where the command is present
AreaTupleType = Tuple[int, int, int, int]

# ##################################
# METADATA special variables

# Simple DC fields not covered:
#  type (controlled),
#  format (controlled),
#  rights (controlled),
#  publisher,
#  contributor,
#  relation
#
# XML Dublin Core: http://www.dublincore.org/documents/dc-xml-guidelines/
# Exhaustive list: http://dublincore.org/documents/dcmi-type-vocabulary/

# Fields: ("<field label in Spreadsheet file>", "<field name in Dublin Core>", Mandatory?, Controlled?, NameInJSON)
metadata_fields = [("Case study name", "title", False, False, "case_study_name"),
                   ("Case study code", "title", True, False, "case_study_code"),
                   ("Title", "title", True, False, "title"),
                   ("Subject, topic and/or keywords", "subject", False, True, "subject_topic_keywords"),
                   ("Description", "description", False, False, "description"),
                   ("Geographical level", "description", True, True, "geographical_level"),
                   ("Dimensions", "subject", True, True, "dimensions"),
                   ("Reference documentation", "source", False, False, "reference_documentation"),
                   ("Authors", "creator", True, False, "authors"),
                   ("Date of elaboration", "date", True, False, "date_of_elaboration"),
                   ("Temporal situation", "coverage", True, False, "temporal_situation"),
                   ("Geographical location", "coverage", True, False, "geographical_situation"),
                   ("DOI", "identifier", False, False, "doi"),
                   ("Language", "language", True, True, "language"),
                   ("Restriction level", None, True, True, "restriction_level"),
                   ("Version", None, True, False, "version")
                   ]

# Regular expression definitions
_var_name = "([a-zA-Z][a-zA-Z0-9_-]*)"
_hvar_name = "(" + _var_name + r"(\." + _var_name + ")*)"
_cplex_var = "((" + _var_name + "::)?" + _hvar_name + ")"
_optional_alphanumeric = "([ a-zA-Z0-9_-]*)?"  # Whitespace also allowed


# Regular expression for "worksheet name" in version 2
def simple_regexp(names: List[str]):
    return r"(" + "|".join(names) + ")" + _optional_alphanumeric

# ##################################
# Commands


@attrs(cmp=False)  # Constant and Hashable by id
class Command:
    # Name
    name = attrib()  # type: str
    # Labels
    labels = attrib()  # type: List[str]
    # Subclass of IExecutableCommand in charge of the execution
    execution_class_name = attrib()  # type: Optional[str]
    # Alternative regular expression for worksheet name
    alt_regex = attrib(default=None)
    # Parse function, having params (Worksheet, Area) and returning a tuple (issues, label, content)
    # Callable[[Worksheet, AreaTupleType, str, ...], IssuesLabelContentTripleType] = attrib(default=None)
    parse_function: Callable[..., IssuesLabelContentTripleType] = attrib(default=None)
    # List of commands fields
    # fields = attrib(default=[])  # type: List[CommandField]
    # In which version is this command allowed?
    is_v1 = attrib(default=False)  # type: bool
    is_v2 = attrib(default=False)  # type: bool

    @property
    def regex(self):
        regexp_pattern = self.alt_regex
        if not regexp_pattern:
            regexp_pattern = simple_regexp(self.labels)

        return re.compile(regexp_pattern, flags=re.IGNORECASE)

    @property
    def label(self):
        return self.labels[0] if self.labels else ""

    @property
    def execution_class(self):
        if self.execution_class_name:
            module_name, class_name = self.execution_class_name.rsplit(".", 1)
            return getattr(importlib.import_module(module_name), class_name)
        else:
            return None


@attrs(cmp=False)  # Constant and Hashable by id
class CommandField:
    # Allowed names for the column
    allowed_names = attrib()  # type: list[str]
    # Internal name used during the parsing
    name = attrib()  # type: str
    # Flag indicating if the column is mandatory or optional
    mandatory = attrib()  # type: bool
    # Parser for the column
    parser = attrib()
    # Some columns have a predefined set of allowed strings
    allowed_values = attrib(default=None)  # type: Optional[list[str]]
    # Many values or just one
    many_values = attrib(default=True)
    # Many appearances (the field can appear multiple times). A convenience to define a list
    many_appearances = attrib(default=False)
    # Examples
    examples = attrib(default=None)  # type: list[str]
    # Compiled regex
    # regex_allowed_names = attrib(default=None)
    # Is it directly an attribute of a Musiasem type? Which one?
    attribute_of = attrib(default=None)  # type: type

    @property
    def regex_allowed_names(self):
        def contains_any(s, setc):
            return 1 in [c in s for c in setc]

        # Compile the regular expressions of column names
        rep = [(r if contains_any(r, ".+") else re.escape(r))+"$" for r in self.allowed_names]

        return re.compile("|".join(rep), flags=re.IGNORECASE)
