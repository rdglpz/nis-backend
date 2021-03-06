import json

from backend.command_generators import Issue
from backend.command_generators.spreadsheet_command_parsers_v2 import IssueLocation
from backend.common.helper import create_dictionary
from backend.model_services import IExecutableCommand, get_case_study_registry_objects
from backend.models.musiasem_concepts import Parameter, ProblemStatement


class ProblemStatementCommand(IExecutableCommand):
    def __init__(self, name: str):
        self._name = name
        self._content = None

    def execute(self, state: "State"):
        any_error = False
        issues = []
        sheet_name = self._content["command_name"]
        # Obtain global variables in state
        glb_idx, p_sets, hh, datasets, mappings = get_case_study_registry_objects(state)

        scenarios = create_dictionary()
        solver_parameters = create_dictionary()

        for r, param in enumerate(self._content["items"]):
            parameter = param["parameter"]
            scenario = param["scenario_name"]
            p = glb_idx.get(Parameter.partial_key(parameter))
            if scenario:
                if len(p) == 0:
                    issues.append(Issue(itype=3,
                                        description="The parameter '" + parameter + "' has not been declared previously.",
                                        location=IssueLocation(sheet_name=sheet_name, row=r, column=None)))
                    any_error = True
                    continue
                p = p[0]
                name = p.name
            else:
                name = parameter
            value = param["parameter_value"]
            description = param.get("description", None)  # For readability of the workbook. Not used for solving
            if scenario:
                if scenario in scenarios:
                    sp = scenarios[scenario]
                else:
                    sp = create_dictionary()
                    scenarios[scenario] = sp
                sp[name] = value
            else:
                solver_parameters[name] = value

        if not any_error:
            ps = ProblemStatement(solver_parameters, scenarios)
            glb_idx.put(ps.key(), ps)

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
