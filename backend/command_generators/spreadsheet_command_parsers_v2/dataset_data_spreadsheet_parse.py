from io import StringIO
from typing import List

import pandas as pd
from openpyxl.worksheet.worksheet import Worksheet

from backend import IssuesLabelContentTripleType, AreaTupleType
from backend.command_generators import Issue, IssueLocation
from backend.common.helper import strcmp, create_dictionary


def parse_dataset_data_command(sh: Worksheet, area: AreaTupleType, name: str, state) -> IssuesLabelContentTripleType:
    """
    Check that the syntax of the input spreadsheet is correct
    Return the analysis in JSON compatible format, for execution

    :param sh:   Input worksheet
    :param area: Area of the input worksheet to be analysed
    :return:     The command in a dict-list object (JSON ready)
    """

    issues: List[Issue] = []

    # Analyze column names
    col_map = create_dictionary()
    for c in range(area[2], area[3]):
        col_name = sh.cell(row=area[0], column=c).value.strip()
        # Avoid repetitions
        if col_name in col_map:
            issues.append(Issue(itype=3,
                                description="The column name '"+col_name+"' is repeated",
                                location=IssueLocation(sheet_name=name, row=1, column=c)))

        if strcmp(col_name, "DatasetName") or strcmp(col_name, "Dataset"):
            col_map["dataset"] = c
        elif col_name:
            # Concept name
            col_map[col_name] = c

    if "dataset" not in col_map:
        issues.append(Issue(itype=3,
                            description="The column name 'DatasetName' is not defined for command 'DatasetData'",
                            location=IssueLocation(sheet_name=name, row=1, column=c)))

    if any([i.itype == 3 for i in issues]):
        return issues, None, None

    # Read all the content into a list of lists
    lines = []
    for r in range(area[0] + 1, area[1]):
        line = []
        for col_name, c in col_map.items():
            v = sh.cell(row=r, column=c).value
            if isinstance(v, str):
                v = v.strip()
            line.append(v)
        lines.append(line)

    # pd.DataFrame
    df = pd.DataFrame(columns=[col_name for col_name in col_map], data=lines)

    # Find the different datasets
    datasets = df["dataset"].unique()
    datasets = set([d.lower() for d in datasets])

    content = []  # The output JSON
    for dataset in datasets:
        # Obtain filtered
        df2 = df.loc[df['dataset'].str.lower() == dataset]
        # Convert to JSON and store in content
        del df2["dataset"]
        s = StringIO()
        df2.to_json(s, orient="split")
        content.append(dict(name=dataset, values=s.getvalue()))

    return issues, None, dict(items=content, command_name=name)

