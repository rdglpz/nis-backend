import importlib
from pyparsing import (ParserElement,
                       oneOf, srange, operatorPrecedence, opAssoc,
                       Forward, Regex, Suppress, Literal, Word,
                       Optional, OneOrMore, ZeroOrMore, Or,
                       Combine, Group, delimitedList, nums, quotedString, NotAny
                       )

from backend.model.memory.musiasem_concepts import ExternalDataset

# Number
# Variable(key=expression, key=expression)[key=expression, key=expression]
# Hierarchical variable name
# Arithmetic Expression

# Tokens
lparen, rparen, lbracket, rbracket, dot, equals, hash = map(Literal, "()[].=#")
quote = oneOf('" ''')
signop = oneOf('+ -')
multop = oneOf('* / // %')
plusop = oneOf('+ -')
simple_ident = Word(srange("[a-zA-Z]"), srange("[a-zA-Z0-9_]"))  # Start in letter, then "_" + letters + numbers

# Basic data types
integer = Word(nums).setParseAction(lambda t: {'type': 'int', 'value': int(t[0])})
real = (Combine(Word(nums) + Optional("." + Word(nums))
                + oneOf("E e") + Optional(oneOf('+ -')) + Word(nums))
        | Combine(Word(nums) + "." + Word(nums))
        ).setParseAction(lambda t: {'type': 'float', 'value': float(t[0])})
string = quotedString.setParseAction(lambda t: {'type': 'str', 'value': t[0]})

# RULES: namespace, parameter list, function call, dataset variable, hierarchical var name
namespace = simple_ident + Literal("::").suppress()
expression = Forward()
named_parameter = Group(simple_ident + equals.suppress() + expression).setParseAction(lambda t: {'type': 'named_parameter', 'param': t[0][0], 'value': t[0][1]})
named_parameters_list = delimitedList(named_parameter, ",")
parameters_list = delimitedList(Or([expression, named_parameter]), ",")
func_call = Group(simple_ident + lparen.suppress() + parameters_list + rparen.suppress()
                  ).setParseAction(lambda t: {'type': 'function',
                                              'name': t[0][0],
                                              'params': t[0][1:]
                                              }
                                   )
dataset = (simple_ident.setResultsName("ident") +
           Optional(lparen.suppress() + parameters_list + rparen.suppress()).setResultsName("func_params") +
           lbracket.suppress() + named_parameters_list.setResultsName("slice_params") + rbracket.suppress()
           ).setParseAction(lambda _s, l, t: {'type': 'dataset',
                                              'name': t.ident,
                                              'func_params': t.func_params if t.func_params else None,
                                              'slice_params': t.slice_params,
                                              }
                            )
# [ns::]dataset"."column_name
dataset_with_column = (Optional(namespace).setResultsName("namespace") +
                       Group(Or([simple_ident]) + dot.suppress() + simple_ident).setResultsName("parts")
                       ).setParseAction(lambda _s, l, t:
                                                         {'type': 'h_var',
                                                          'ns': t.namespace[0] if t.namespace else None,
                                                          'parts': t.parts.asList(),
                                                          }
                                        )
obj_types = Or([simple_ident, func_call, dataset])
# h_name, the most complex NAME, which can be a hierarchical composition of names, function calls and datasets
h_name = (Optional(namespace).setResultsName("namespace") +
          Group(obj_types + ZeroOrMore(dot.suppress() + obj_types)).setResultsName("parts")
          # + Optional(hash + simple_ident).setResultsName("part")
          ).setParseAction(lambda _s, l, t: {'type': 'h_var',
                                             'ns': t.namespace[0] if t.namespace else None,
                                             'parts': t.parts.asList(),
                                             }
                           )

# This one is the same as "h_name", but instead of "obj_types" uses "simple_ident": no function calls or datasets allowed
simple_h_name = (Optional(namespace).setResultsName("namespace") +
                 Group(simple_ident + ZeroOrMore(dot.suppress() + simple_ident)).setResultsName("ident")
                 ).setParseAction(lambda _s, l, t: {'type': 'h_var',
                                                    'ns': t.namespace[0] if t.namespace else None,
                                                    'parts': t.ident.asList(),
                                                    }
                                  )

# RULES: Expression

operand = Or([real, integer, string, h_name])

expression << operatorPrecedence(operand,
                                 [(signop, 1, opAssoc.RIGHT, lambda _s, l, t: {'type': 'u'+t.asList()[0][0], 'terms': [0, t.asList()[0][1]], 'ops': ['u'+t.asList()[0][0]]}),
                                  (multop, 2, opAssoc.LEFT, lambda _s, l, t: {'type': 'multipliers', 'terms': t.asList()[0][0::2], 'ops': t.asList()[0][1::2]}),
                                  (plusop, 2, opAssoc.LEFT, lambda _s, l, t: {'type': 'adders', 'terms': t.asList()[0][0::2], 'ops': t.asList()[0][1::2]}),
                                  ],
                                 lpar=lparen.suppress(),
                                 rpar=rparen.suppress())

# RULES: Level name
level_name = (simple_ident + Optional(plusop+integer)
              ).setParseAction(lambda t: {'type': 'level', 'domain': t[0], 'level': t[1][0]+t[1][1] if t[1] else None})

# RULES: Time expression
# A valid time specification. Possibilities: Year, Month-Year / Year-Month, Time span (two dates)
four_digits_year = Word(nums, min=4, max=4)
month = Word(nums, min=1, max=2)
year_month_separator = oneOf("- /")
date = Group(Or([four_digits_year.setResultsName("y") +
                 Optional(year_month_separator.suppress()+month.setResultsName("m")),
                 Optional(month.setResultsName("m") + year_month_separator.suppress()) +
                 four_digits_year.setResultsName("y")
                 ]
                )
             )
two_dates_separator = oneOf("- /")
time_expression = (date + Optional(two_dates_separator.suppress()+date)
                   ).setParseAction(
                                    lambda _s, l, t:
                                    {'type': 'time',
                                     'dates': [{k: int(v) for k, v in d.items()} for d in t]
                                     }
                                    )

# #################################################################################################################### #

# List of Global Functions

f = [{"name": "cos", "full_name": "math.cos", "kwargs": None},
     {"name": "sin", "full_name": "math.sin", "kwargs": None}
     ]

global_functions = {i["name"]: i for i in f}


def ast_evaluator(exp, state, obj, issue_lst, evaluation_type):
    """
    Numerically evaluate the result of the parse of the previous "expression" rule

    :param exp: Input dictionary
    :param state: State used to obtain variables/objects
    :param obj: An object used when evaluating hierarchical variables. simple names, functions and datasets are considered members of this object
    :param issue_lst: List in which issues have to be annotated
    :param evaluation_type: "numeric" for full evaluation, "static" to return True if the expression can be evaluated
            (explicitly mentioned variables are defined previously)
    :return: value (scalar EXCEPT for named parameters, which return a tuple "parameter name - parameter value"
    """
    val = None
    if "type" in exp:
        t = exp["type"]
        if t in ("int", "float", "str"):
            if evaluation_type == "numeric":
                return exp["value"]
            elif evaluation_type == "static":
                return True
        elif t == "named_parameter":
            # This one returns a tuple (parameter name, parameter value)
            return exp["param"], ast_evaluator(exp["value"], state, obj, issue_lst, evaluation_type)
        elif t == "dataset":
            # Function parameters and Slice parameters
            func_params = [ast_evaluator(p, state, obj, issue_lst, evaluation_type) for p in exp["func_params"]]
            slice_params = [ast_evaluator(p, state, obj, issue_lst, evaluation_type) for p in exp["slice_params"]]

            if evaluation_type == "numeric":
                # Find dataset named "exp["name"]"
                if obj is None:
                    # Global dataset
                    ds = state.get(exp["name"], exp["ns"])
                    if not ds:
                        issue_lst.append((3, "Global dataset '" + exp["name"] + "' not found"))
                else:
                    # Dataset inside "obj"
                    try:
                        ds = getattr(obj, exp["name"])
                    except:
                        ds = None
                    if not ds:
                        issue_lst.append((3, "Dataset '" + exp["name"] + "' local to "+str(obj)+" not found"))

                if ds and isinstance(ds, ExternalDataset):
                    return ds.get_data(None, slice_params, None, None, func_params)
                else:
                    return None
            elif evaluation_type == "static":
                # Find dataset named "exp["name"]"
                if obj is None:
                    # Global dataset
                    ds = state.get(exp["name"], exp["ns"])
                    if not ds:
                        issue_lst.append((3, "Global dataset '" + exp["name"] + "' not found"))
                    else:
                        ds = True
                else:
                    ds = True  # We cannot be sure it will be found, but do not break the evaluation
                # True if the Dataset is True, and the parameters are True
                return ds and all(func_params) and all(slice_params)
        elif t == "function":  # Call function
            # First, obtain the Parameters
            args = []
            kwargs = {}
            for p in [ast_evaluator(p, state, obj, issue_lst, evaluation_type) for p in exp["params"]]:
                if isinstance(p, tuple):
                    kwargs[p[0]] = p[1]
                else:
                    args.append(p)

            if evaluation_type == "numeric":
                if obj is None:
                    # Check if global function exists, then call it. There are no function namespaces (at least for now)
                    if exp["name"] in global_functions:
                        _f = global_functions[exp["name"]]
                        mod_name, func_name = _f["full_name"].rsplit('.', 1)
                        mod = importlib.import_module(mod_name)
                        func = getattr(mod, func_name)
                        if _f["kwargs"]:
                            kwargs.update(_f["kwargs"])
                        obj = func(*args, *kwargs)
                else:
                    # Call local function (a "method")
                    try:
                        obj = getattr(obj, exp["name"])
                        obj = obj(*args, **kwargs)
                    except:
                        obj = None
                return obj
            elif evaluation_type == "static":
                if obj is None:
                    # Check if global function exists, then call it. There are no function namespaces (at least for now)
                    if exp["name"] in global_functions:
                        _f = global_functions[exp["name"]]
                        mod_name, func_name = _f["full_name"].rsplit('.', 1)
                        mod = importlib.import_module(mod_name)
                        func = getattr(mod, func_name)
                        # True if everything is True: function defined and all parameters are True
                        obj = func and all(args) and all(kwargs.values())
                else:
                    # Call local function (a "method")
                    obj = True
                return obj
        elif t == "h_var":
            # Evaluate in sequence
            obj = None
            _namespace = exp["ns"]
            for o in exp["parts"]:
                if isinstance(o, str):
                    # Simple name
                    if obj is None:
                        obj = state.get(o, _namespace)
                        if not obj:
                            issue_lst.append((3, "'" + o + "' is not globally declared in namespace '" + _namespace if _namespace else "default" + "'"))
                    else:
                        if isinstance(obj, ExternalDataset):
                            # Check if "o" is column (measure) or dimension
                            if o in obj.get_columns() or o in obj.get_dimensions():
                                obj = obj.get_data(o, None)
                            else:
                                issue_lst.append((3, "'" + o + "' is not a measure or dimension of the dataset."))
                        else:
                            try:
                                obj = getattr(obj, o)
                            except:
                                issue_lst.append((3, "'" + o + "' is not a ."))
                else:
                    # Dictionary: function call or dataset access
                    if obj is None:
                        o["ns"] = _namespace
                    obj = ast_evaluator(o, state, obj, issue_lst, evaluation_type)
            if obj is None or isinstance(obj, (str, int, float)):
                return obj
            # TODO elif isinstance(obj, ...) depending on core object types, invoke a default method, or issue ERROR if it is not possible to cast to something simple
            else:
                return obj
        elif t in ("u+", "u-", "multipliers", "adders"):  # Arithmetic OPERATIONS
            # Evaluate recursively the left and right operands
            if t in ("u+", "u-"):
                if evaluation_type == "numeric":
                    current = 0
                else:
                    current = True
            else:
                current = ast_evaluator(exp["terms"][0], state, obj, issue_lst, evaluation_type)
            for i, e in enumerate(exp["terms"][1:]):
                following = ast_evaluator(e, state, obj, issue_lst, evaluation_type)

                if evaluation_type == "numeric":
                    # Type casting for primitive types
                    # TODO For Object types, apply default conversion. If both sides are Object, assume number
                    if (isinstance(current, (int, float)) and isinstance(following, (int, float))) or \
                            (isinstance(current, str) and isinstance(following, str)):
                        pass  # Do nothing
                    elif isinstance(current, (int, float)) and isinstance(following, str):
                        if isinstance(current, int):
                            following = int(following)
                        else:
                            following = float(following)
                    elif isinstance(current, str) and isinstance(following, (int, float)):
                        if isinstance(following, int):
                            current = int(current)
                        else:
                            current = float(current)

                    op = exp["ops"][i]
                    if op in ("+", "-", "u+", "u-"):
                        if current is None:
                            current = 0
                        if following is None:
                            following = 0
                        if op in ("-", "u-"):
                            following = -following

                        current += following
                    else:
                        if following is None:
                            following = 1
                        if current is None:
                            current = 1
                        if op == "*":
                            current *= following
                        elif op == "/":
                            current /= following
                        elif op == "//":
                            current //= following
                        elif op == "%":
                            current %= following
                elif evaluation_type == "static":
                    current = current and following

            return current
        else:
            issue_lst.append((3, "'type' = "+t+" not supported."))
    else:
        issue_lst.append((3, "'type' not present in "+str(exp)))

    return val


def string_to_ast(rule: ParserElement, input_: str):
    res = rule.parseString(input_, parseAll=True)
    res = res.asList()[0]
    while isinstance(res, list):
        res = res[0]
    return res


if __name__ == '__main__':
    from backend.model_services import State
    from dotted.collection import DottedDict

    s = "ds.col"
    res = string_to_ast(h_name, s)

    s = State()
    examples = [
        "2017-05 - 2018-01",
        "2017",
        "5-2017",
        "5-2017 - 2018-1",
        "2017-2018"
    ]
    for example in examples:
        print(example)
        res = string_to_ast(time_expression, example)
        print(res)
        print("-------------------")

    s.set("HH", DottedDict({"Power": {"p": 34.5, "Price": 2.3}}))
    s.set("EN", DottedDict({"Power": {"Price": 1.5}}))
    s.set("HH", DottedDict({"Power": 25}), "ns2")
    s.set("param1", 0.93)
    s.set("param2", 0.9)
    s.set("param3", 0.96)
    examples = [
        "EN(p1=1.5, p2=2.3)[d1='C11', d2='C21'].v1",  # Simply sliced Variable Dataset (function call)
        "a_function(p1=2, p2='cc', p3=1.3*param3)",
        "-5+4*2",  # Simple expression #1
        "HH",  # Simple name
        "HH.Power.p",  # Hierarchic name
        "5",  # Integer
        "1.5",  # Float
        "1e-10",  # Float scientific notation
        "(5+4)*2",  # Simple expression #2 (parenthesis)
        "3*2/6",  # Simple expression #3 (consecutive operators of the same kind)
        "'hello'",  # String
        "ns2::HH.Power",  # Hierarchic name from another Namespace
        "HH.Power.Price + EN.Power.Price * param1",
        "EN[d1='C11', d2='C21'].d1",  # Simple Dataset slice
        "b.a_function(p1=2, p2='cc', p3=1.3*param3)",
        "b.EN[d1='C11', d2='C21'].d1",  # Hierachical Dataset slice
        "tns::EN(p1=1.5+param2, p2=2.3 * 0.3)[d1='C11', d2='C21'].v1",  # Simply sliced Variable Dataset (function call)
    ]
    for example in examples:
        print(example)
        res = string_to_ast(expression, example)
        print(res)
        issues = []
        value = ast_evaluator(res, s, None, issues)
        print(str(type(value))+": "+str(value))
