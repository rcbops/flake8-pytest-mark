# -*- coding: utf-8 -*-

# ======================================================================================================================
# Imports
# ======================================================================================================================
import ast
import re
from uuid import UUID
from collections import namedtuple

# ======================================================================================================================
# Globals
# ======================================================================================================================
_ValueInfo = namedtuple('_ValueInfo', ['node', 'file_path'])
_unique_value_collision_map = {}     # { str('rule_name'): { str('value': _ValueInfo } }


# ======================================================================================================================
# Rules
# ======================================================================================================================
# noinspection PyUnusedLocal
def rule_m3xx(node, rule_name, rule_conf, class_type, filename, **kwargs):
    """Validate that pytest mark rules configured with 'enforce_unique_value' option will allow only unique values
    for the mark across all files being processed during a single flake8 run.

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        filename (str): The name of the file to evaluate.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """

    error_msg = ''
    line_num = node.lineno
    enforce = True if 'enforce_unique_value' in rule_conf and rule_conf['enforce_unique_value'].lower() == 'true' \
        else False

    if enforce:
        for decorator in _reduce_decorators_by_mark(node.decorator_list, rule_conf['name']):
            values = _get_decorator_args(decorator)
            for value in values:
                if rule_name not in _unique_value_collision_map:
                    _unique_value_collision_map[rule_name] = {value: _ValueInfo(node, filename)}
                elif value in _unique_value_collision_map[rule_name]:
                    error_msg += ("The '{}' mark value already specified for the '{}' test at line '{}' found in the "
                                  "'{}' file! ".format(value,
                                                       _unique_value_collision_map[rule_name][value].node.name,
                                                       _unique_value_collision_map[rule_name][value].node.lineno,
                                                       _unique_value_collision_map[rule_name][value].file_path))
                else:
                    _unique_value_collision_map[rule_name][value] = _ValueInfo(node, filename)

    if error_msg:
        code = _generate_mark_code(rule_name)
        message = "M3{} @pytest.mark.{} value is not unique! {}".format(code, rule_conf['name'], error_msg.rstrip())
        yield (line_num, 0, message, class_type)


# noinspection PyUnusedLocal
def rule_m5xx(node, rule_name, rule_conf, class_type, **kwargs):
    """Read and validate the input file contents.
    A 5XX rule checks for the presence of a configured 'pytest_mark'
    Marks may be numbered up to 50, example: 'pytest_mark49'

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """
    line_num = node.lineno
    code = _generate_mark_code(rule_name)
    message = 'M5{} test definition not marked with {}'.format(code, rule_conf['name'])
    if not _reduce_decorators_by_mark(node.decorator_list, rule_conf['name']):
        yield (line_num, 0, message, class_type)


# noinspection PyUnusedLocal
def rule_m6xx(node, rule_name, rule_conf, class_type, **kwargs):
    """Validate a value to a given mark against a provided regex
    A 6XX requires a configured 5XX rule
    A 6XX rule will not warn if a corresponding 5XX rule validates

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """

    non_matching_values = []
    detailed_error = None
    line_num = node.lineno

    for decorator in _reduce_decorators_by_mark(node.decorator_list, rule_conf['name']):
        values = _get_decorator_args(decorator)

        if any(k in rule_conf for k in ('value_regex', 'value_match')):
            if len(values) == 0:
                non_matching_values.append('')
                detailed_error = "Validation supplied, but values absent."
            # iterate through values to test all for matching
            for value in values:
                if 'value_regex' in rule_conf:
                    if not re.match(rule_conf['value_regex'], value):
                        non_matching_values.append(value)
                        detailed_error = "Configured regex: '{}'".format(rule_conf['value_regex'])

                # only use match if regex is not supplied
                if 'value_match' in rule_conf and 'value_regex' not in rule_conf:
                    if rule_conf['value_match'] == 'uuid':
                        try:
                            UUID(value)
                        # excepting Exception intentionally here
                        # If UUID can't parse the value for any reason its not a valid uuid
                        except Exception as e:
                            non_matching_values.append(value)
                            detailed_error = e

    if non_matching_values:
        code = _generate_mark_code(rule_name)
        message = ("M6{} the mark values '{}' "
                   "do not match the configuration "
                   "specified by {}, {}".format(code, non_matching_values, rule_name, detailed_error))
        yield (line_num, 0, message, class_type)


# noinspection PyUnusedLocal
def rule_m7xx(node, rule_name, rule_conf, class_type, **kwargs):
    """Validate types of the objects passed as args to a configured mark
    All args must be strings

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """

    line_num = node.lineno
    code = _generate_mark_code(rule_name)
    message = False
    for decorator in _reduce_decorators_by_mark(node.decorator_list, rule_conf['name']):
        if isinstance(decorator, ast.Call):
            if any(not isinstance(arg, ast.Str) for arg in decorator.args):
                message = 'M7{} mark values must be strings'.format(code)
    if message:
        yield (line_num, 0, message, class_type)


# noinspection PyUnusedLocal
def rule_m8xx(node, rule_name, rule_conf, class_type, **kwargs):
    """Validates that @pytest.mark.foo() is only called once for a given test
    On by default, can be turned off with allow_duplicate=true

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """

    line_num = node.lineno
    code = _generate_mark_code(rule_name)
    message = 'M8{} @pytest.mark.{} may only be called once for a given test'.format(code, rule_conf['name'])
    allow_dupe = True if 'allow_duplicate' in rule_conf and rule_conf['allow_duplicate'].lower() == 'true' else False
    if not allow_dupe and len(_reduce_decorators_by_mark(node.decorator_list, rule_conf['name'])) > 1:
        yield (line_num, 0, message, class_type)


# noinspection PyUnusedLocal
def rule_m9xx(node, rule_name, rule_conf, class_type, **kwargs):
    """Validates the number of arguments to @pytest.mark.foo()
    By default we validate that there is only one argument
    can configure to allow multiple with allow_multiple_args=true

    Args:
        node (ast.AST): A node in the ast.
        rule_name (str): The name of the rule.
        rule_conf (dict): The dictionary containing the properties of the rule.
        class_type (class): The class that this rule was called from.
        kwargs (dict): A dictionary of keyword arguments.

    Yields:
        tuple: (int, int, str, type) the tuple used by flake8 to construct a violation.
    """

    line_num = node.lineno
    code = _generate_mark_code(rule_name)
    allow_multiple_args = False
    if 'allow_multiple_args' in rule_conf and rule_conf['allow_multiple_args'].lower() == 'true':
        allow_multiple_args = True
    for decorator in _reduce_decorators_by_mark(node.decorator_list, rule_conf['name']):
        if isinstance(decorator, ast.Call):
            if not allow_multiple_args and len(decorator.args) > 1:
                message = 'M9{} you may only specify one argument to @pytest.mark.{}'.format(code, rule_conf['name'])
                yield (line_num, 0, message, class_type)


# ======================================================================================================================
# Private Functions
# ======================================================================================================================
def _reduce_decorators_by_mark(decorators, mark):
    """reduces a list of decorators to a list that
    are decorators used by pytest
    are decorators of the mark passed in

    Args:
        decorators (list): A list of decorators from AST
        mark (str): The name of the mark.

    Returns:
        list: decorators that are 'pytest' and the passed mark
    """
    reduced = []
    for decorator in decorators:
        if isinstance(decorator, ast.Call):
            try:
                if decorator.func.attr == mark and decorator.func.value.value.id == 'pytest':
                    reduced.append(decorator)
            except AttributeError:
                pass
        elif isinstance(decorator, ast.Attribute):
            try:
                if decorator.attr == mark:
                    reduced.append(decorator)
            except AttributeError:
                pass
    return reduced


def _get_decorator_args(decorator):
    """Gets the string arguments for a given decorator

    Args:
        decorator (AST.node.decorator): A decorator

    Returns:
        list: a list of args that are strings from the passed decorator
    """
    args = []
    try:
        for arg in decorator.args:
            args.append(arg.s)
    except AttributeError:
        pass
    return args


def _generate_mark_code(rule_name):
    """Generates a two digit string based on a provided string

    Args:
        rule_name (str): A configured rule name 'pytest_mark3'.

    Returns:
        str: A two digit code based on the provided string '03'
    """
    code = ''.join([i for i in str(rule_name) if i.isdigit()])
    code = code.zfill(2)
    return code
