"""
Evaluation of ASTs

Ideas copied/adapted from:
https://gist.github.com/cynici/5865326

"""
import importlib
from typing import Dict
from pyparsing import quotedString

from backend.model_services import State
from backend.command_generators.parser_field_parsers import string_to_ast, arith_boolean_expression, key_value_list, \
    simple_ident, expression_with_parameters
from backend.common.helper import create_dictionary, PartialRetrievalDictionary
from backend.models.musiasem_concepts import ExternalDataset


# #################################################################################################################### #

# List of Global Functions

global_functions = {i["name"]: i for i in
                    [{"name": "cos", "full_name": "math.cos", "kwargs": None},
                     {"name": "sin", "full_name": "math.sin", "kwargs": None}
                     ]
                    }

# Comparison operators
opMap = {
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "==": lambda a, b: a == b,
        "=": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<>": lambda a, b: a != b,
        }


def ast_evaluator(exp: Dict, state: State, obj, issue_lst, evaluation_type="numeric"):
    """
    Numerically evaluate the result of the parse of "expression" rule (not valid for the other "expression" rules)

    :param exp: Dictionary representing the AST (output of "string_to_ast" function)
    :param state: "State" used to obtain variables/objects
    :param obj: An object used when evaluating hierarchical variables. simple names, functions and datasets are considered members of this object
    :param issue_lst: List in which issues have to be annotated
    :param evaluation_type: "numeric" for full evaluation, "static" to return True if the expression can be evaluated
            (explicitly mentioned variables are defined previously)
    :return: value (scalar EXCEPT for named parameters, which return a tuple "parameter name - parameter value"), list of unresolved variables
    """
    val = None
    unresolved_vars = set()
    if "type" in exp:
        t = exp["type"]
        if t in ("int", "float", "str", "boolean"):
            if evaluation_type == "numeric":
                return exp["value"], unresolved_vars
            elif evaluation_type == "static":
                return unresolved_vars
        elif t == "named_parameter":
            # This one returns a tuple (parameter name, parameter value, unresolved variables)
            v, tmp = ast_evaluator(exp["value"], state, obj, issue_lst, evaluation_type)
            unresolved_vars.update(tmp)
            return exp["param"], v, unresolved_vars
        elif t == "key_value_list":
            d = create_dictionary()
            for k, v in exp["parts"].items():
                d[k], tmp = ast_evaluator(v, state, obj, issue_lst, evaluation_type)
                unresolved_vars.update(tmp)
            return d, unresolved_vars
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
            can_resolve = True
            for p in [ast_evaluator(p, state, obj, issue_lst, evaluation_type) for p in exp["params"]]:
                if len(p) == 3:
                    kwargs[p[0]] = p[1]
                    tmp = p[2]
                else:
                    args.append(p[0])
                    tmp = p[1]
                unresolved_vars.update(tmp)
                if len(tmp) > 0:
                    can_resolve = False

            if evaluation_type == "numeric":
                if obj is None:
                    # Check if it can be resolved (all variables specified)
                    # Check if global function exists, then call it. There are no function namespaces (at least for now)
                    if can_resolve and exp["name"] in global_functions:
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
                return obj, unresolved_vars
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
            _namespace = exp.get("ns", None)
            for o in exp["parts"]:
                if isinstance(o, str):
                    # Simple name
                    if obj is None:
                        obj = state.get(o, _namespace)
                        if not obj:
                            issue_lst.append((3, "'" + o + "' is not globally declared in namespace '" + (_namespace if _namespace else "default") + "'"))
                            if _namespace:
                                unresolved_vars.add(_namespace+"::"+o)
                            else:
                                unresolved_vars.add(o)
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
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return obj, unresolved_vars
            # TODO elif isinstance(obj, ...) depending on core object types, invoke a default method, or
            #  issue ERROR if it is not possible to cast to something simple
            else:
                return obj, unresolved_vars
        elif t == "condition":  # Evaluate IF part to a Boolean. If True, return the evaluation of the THEN part; if False, return None
            if_result, tmp = ast_evaluator(exp["if"], state, obj, issue_lst, evaluation_type)
            unresolved_vars.update(tmp)
            if len(tmp) == 0:
                if if_result:
                    then_result, tmp = ast_evaluator(exp["then"], state, obj, issue_lst, evaluation_type)
                    unresolved_vars.update(tmp)
                    if len(tmp) > 0:
                        then_result = None
                    return then_result, unresolved_vars
            else:
                return None, unresolved_vars
        elif t == "conditions":
            for c in exp["parts"]:
                cond_result, tmp = ast_evaluator(c, state, obj, issue_lst, evaluation_type)
                unresolved_vars.update(tmp)
                if len(tmp) == 0:
                    if cond_result:
                        return cond_result, unresolved_vars
            return None, unresolved_vars
        elif t == "reference":
            return "[" + exp["ref_id"] + "]", unresolved_vars  # TODO Return a special type
        elif t in ("u+", "u-", "multipliers", "adders", "comparison", "not", "and", "or"):  # Arithmetic and Boolean
            # Evaluate recursively the left and right operands
            if t in ("u+", "u-"):
                if evaluation_type == "numeric":
                    current = 0
                else:
                    current = True
            else:
                current, tmp1 = ast_evaluator(exp["terms"][0], state, obj, issue_lst, evaluation_type)
                unresolved_vars.update(tmp1)

            for i, e in enumerate(exp["terms"][1:]):
                following, tmp2 = ast_evaluator(e, state, obj, issue_lst, evaluation_type)
                unresolved_vars.update(tmp2)

                if len(tmp1) == 0 and len(tmp2) == 0:
                    if evaluation_type == "numeric":
                        # Type casting for primitive types
                        # TODO For Object types, apply default conversion. If both sides are Object, assume number
                        if (isinstance(current, (int, float)) and isinstance(following, (int, float))) or \
                                (isinstance(current, bool) and isinstance(following, bool)) or \
                                (isinstance(current, str) and isinstance(following, str)):
                            pass  # Do nothing
                        else:  # In others cases, CAST to the operand of the left. This may result in an Exception
                            following = type(current)(following)

                        op = exp["ops"][i].lower()
                        if op in ("+", "-", "u+", "u-"):
                            if current is None:
                                current = 0
                            if following is None:
                                following = 0
                            if op in ("-", "u-"):
                                following = -following

                            current += following
                        elif op in ("*", "/", "//", "%"):
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
                        elif op == "not":
                            current = not bool(following)
                        elif op == "and":
                            current = current and following
                        elif op == "or":
                            current = current or following
                        else:  # Comparators
                            fn = opMap[op]
                            current = fn(current, following)
                    elif evaluation_type == "static":
                        current = current and following
                else:
                    current = None  # Could not evaluate because there are missing variables

            return current, unresolved_vars
        else:
            issue_lst.append((3, "'type' = "+t+" not supported."))
    else:
        issue_lst.append((3, "'type' not present in "+str(exp)))

    return val, unresolved_vars


def ast_to_string(exp):
    """
    Elaborate string from expression AST

    :param exp: Input dictionary
    :return: value (scalar EXCEPT for named parameters, which return a tuple "parameter name - parameter value"
    """
    val = None
    if "type" in exp:
        t = exp["type"]
        if t in ("int", "float", "str"):
            val = str(exp["value"])
        elif t == "named_parameter":
            val = str(exp["param"] + "=" + ast_to_string(exp["value"]))
        elif t == "pf_name":
            val = str(exp["processor"] if exp["processor"] else "") + (":" + exp["factor"]) if exp["factor"] else ""
        elif t == "dataset":
            # Function parameters and Slice parameters
            func_params = [ast_to_string(p) for p in exp["func_params"]]
            slice_params = [ast_to_string(p) for p in exp["slice_params"]]

            val = exp["name"]
            if func_params:
                val += "(" + ", ".join(func_params) + ")"
            if slice_params:
                val += "[" + ", ".join(slice_params) + "]"
        elif t == "function":  # Call function
            # First, obtain the Parameters
            val = exp["name"]
            params = []
            for p in [ast_to_string(p) for p in exp["params"]]:
                if isinstance(p, tuple):
                    params.append(p[0] + "=" + p[1])
                else:
                    params.append(p)
            val += "(" + ", ".join(params) + ")"
        elif t == "h_var":
            # Evaluate in sequence
            _namespace = exp["ns"] if "ns" in exp else None
            if _namespace:
                val = _namespace + "::"
            else:
                val = ""

            parts = []
            for o in exp["parts"]:
                if isinstance(o, str):
                    parts.append(o)
                else:
                    # Dictionary: function call or dataset access
                    parts.append(ast_to_string(o))
            val += ".".join(parts)
        elif t in ("u+", "u-", "multipliers", "adders"):  # Arithmetic OPERATIONS
            # Evaluate recursively the left and right operands
            if t in "u+":
                current = ""
            elif t == "u-":
                current = "-"
            else:
                current = ast_to_string(exp["terms"][0])

            for i, e in enumerate(exp["terms"][1:]):
                following = ast_to_string(e)

                op = exp["ops"][i]
                if op in ("+", "-", "u+", "u-"):
                    if current is None:
                        current = 0
                    if following is None:
                        following = 0
                    if op in ("-", "u-"):
                        following = "-(" + following + ")"

                    current = "(" + current + ") + (" + following + ")"
                elif op in ("*", "/", "//", "%"):  # Multipliers
                    if following is None:
                        following = "1"
                    if current is None:
                        current = "1"
                    if op == "*":
                        current = "(" + current + ") * (" + following + ")"
                    elif op == "/":
                        current = "(" + current + ") / (" + following + ")"
                    elif op == "//":
                        current = "(" + current + ") // (" + following + ")"
                    elif op == "%":
                        current = "(" + current + ") % (" + following + ")"
                elif op == "not":
                    if following is None:
                        following = "True"
                    current = "Not (" + following + ")"
                else:  # And, Or, Comparators
                    if following is None:
                        following = "True"
                    if current is None:
                        current = "True"
                    current = "(" + current + ") " + op + "(" + following + ")"

            val = current

    return val


def dictionary_from_key_value_list(kvl, state: State = None):
    """
    From a string containing a list of keys and values, return a dictionary
    Keys must be literals, values can be expressions, to be evaluated at a later moment

    (syntactic validity of expressions is not checked here)

    :param kvl: String containing the list of keys and values
    :except If syntactic problems occur
    :return: A dictionary
    """
    pairs = kvl.split(",")
    d = create_dictionary()
    for p in pairs:
        k, v = p.split("=", maxsplit=1)
        if not k:
            raise Exception(
                "Each key-value pair must be separated by '=' and key has to be defined, value can be empty: " + kvl)
        else:
            try:
                k = k.strip()
                v = v.strip()
                string_to_ast(simple_ident, k)
                try:
                    # Simplest: string
                    string_to_ast(quotedString, v)
                    v = v[1:-1]
                except:
                    issues = []
                    ast = string_to_ast(expression_with_parameters, v)
                    res, unres = ast_evaluator(ast, state, None, issues)
                    if len(unres) == 0:
                        v = res

                d[k] = v
            except:
                raise Exception("Key must be a string: " + k + " in key-value list: " + kvl)
    return d


if __name__ == '__main__':
    from backend.model_services import State
    from dotted.collection import DottedDict

    issues = []
    s = State()
    ex = "level =”N - 1”, farm_type =”GH”, efficiency = 0.3"
    ast = string_to_ast(key_value_list, ex)
    res, unres = ast_evaluator(ast, s, None, issues)
    s.set("Param1", 2.1)
    # s.set("Param", 0.1)
    s.set("Param2", 0.2)
    s.set("p1", 2.3)

    ej = "level='n+1', r=[Ref2019], a=5*p1, c=?p1>3 -> 'T1', p1<=3 -> 'T2'?"
    ast = string_to_ast(key_value_list, ej)
    res, unres = ast_evaluator(ast, s, None, issues)

    examples = ["?Param1 > 3 -> 5, Param1 <=3 -> 2?",
                "(Param1 * 3 >= 0.3) AND (Param2 * 2 <= 0.345)",
                "cos(Param*3.1415)",
                "{Param} * 3 >= 0.3",
                "'Hola'",
                "'Hola' + 'Adios'",
                "5 * {Param1}",
                "True",
                "'Hola' + Param1"
    ]
    for e in examples:
        try:
            ast = string_to_ast(arith_boolean_expression, e)
            issues = []
            res, unres = ast_evaluator(ast, s, None, issues)
            print(e+":: AST: "+str(ast))
            if len(unres) > 0:
                print("Unresolved variables: "+str(unres))
            else:
                print(str(type(res)) + ": " + str(res))
        except Exception as e2:
            print("Incorrect: "+e+": "+str(e2))

    s.set("HH", DottedDict({"Power": {"p": 34.5, "Price": 2.3}}))
    s.set("EN", DottedDict({"Power": {"Price": 1.5}}))
    s.set("HH", DottedDict({"Power": 25}), "ns2")
    s.set("param1", 0.93)
    s.set("param2", 0.9)
    s.set("param3", 0.96)
    examples = [
        "EN(p1=1.5, p2=2.3)[d1='C11', d2='C21'].v2",  # Simply sliced Variable Dataset (function call)
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
        "tns::EN(p1=1.5+param2, p2=2.3 * 0.3)[d1='C11', d2='C21'].v2",  # Simply sliced Variable Dataset (function call)
    ]
    for example in examples:
        print(example)
        res = string_to_ast(arith_boolean_expression, example)
        print(res)
        issues = []
        value, unres = ast_evaluator(res, s, None, issues)
        print(str(type(value))+": "+str(value)+"; unresolved: "+unres)
