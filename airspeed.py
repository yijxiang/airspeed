#!/usr/bin/env python

import re, operator

try: import cStringIO as StringIO
except ImportError: import StringIO

__all__ = ['Template', 'TemplateError', 'TemplateSyntaxError', 'FileLoader']


###############################################################################
# Public interface
###############################################################################

class Template:
    def __init__(self, content):
        self.content = content
        self.root_element = None

    def merge(self, namespace, loader=None):
        output = StringIO.StringIO()
        self.merge_to(namespace, output, loader)
        return output.getvalue()

    def merge_to(self, namespace, fileobj, loader=None):
        if loader is None: loader = NullLoader()
        if not self.root_element:
            self.root_element = TemplateBody(self.content)
        self.root_element.evaluate(namespace, fileobj, loader)

class TemplateError(Exception):
    pass

class TemplateSyntaxError(TemplateError):
    def __init__(self, element, expected):
        self.element = element
        self.text_understood = element.full_text()[:element.end]
        self.line = 1 + self.text_understood.count('\n')
        self.column = len(self.text_understood) - self.text_understood.rfind('\n')
        got = element.next_text()
        if len(got) > 40:
            got = got[:36] + ' ...'
        Exception.__init__(self, "line %d, column %d: expected %s, got: %s ..." % (self.line, self.column, expected, got))

    def get_position_strings(self):
        error_line_start = 1 + self.text_understood.rfind('\n')
        if '\n' in self.element.next_text():
            error_line_end = self.element.next_text().find('\n') + self.element.end
        else:
            error_line_end = len(self.element.full_text())
        error_line = self.element.full_text()[error_line_start:error_line_end]
        caret_pos = self.column
        return [error_line, ' ' * (caret_pos - 1) + '^']


class NullLoader:
    def merge_text(self, name, stream):
        raise self.load_template(name)

    def load_template(self, name):
        raise TemplateError("no loader available for '%s'" % name)


class FileLoader:
    def merge_text(self, name, stream):
        f = open(name)
        try: stream.write(f.read())
        finally: f.close()

    def load_template(self, name):
        f = open(name)
        try: return Template(f.read())
        finally: f.close()


###############################################################################
# Internals
###############################################################################

class NoMatch(Exception): pass


class LocalNamespace(dict):
    def __init__(self, parent):
        dict.__init__(self)
        self.parent = parent

    def __getitem__(self, key):
        try: return dict.__getitem__(self, key)
        except KeyError: return self.parent[key]

    def __repr__(self):
        return dict.__repr__(self) + '->' + repr(self.parent)


class _Element:
    def __init__(self, text, start=0):
        self._full_text = text
        self.start = self.end = start
        self.parse()

    def next_text(self):
        return self._full_text[self.end:]

    def my_text(self):
        return self._full_text[self.start:self.end]

    def full_text(self):
        return self._full_text

    def syntax_error(self, expected):
        return TemplateSyntaxError(self, expected)

    def identity_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m: raise NoMatch()
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def next_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m: return False
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def optional_match(self, pattern):
        m = pattern.match(self._full_text, self.end)
        if not m: return False
        self.end = m.start(pattern.groups)
        return True

    def require_match(self, pattern, expected):
        m = pattern.match(self._full_text, self.end)
        if not m: raise self.syntax_error(expected)
        self.end = m.start(pattern.groups)
        return m.groups()[:-1]

    def next_element(self, element_spec):
        if callable(element_spec):
            element = element_spec(self._full_text, self.end)
            self.end = element.end
            return element
        else:
            for element_class in element_spec:
                try: element = element_class(self._full_text, self.end)
                except NoMatch: pass
                else:
                    self.end = element.end
                    return element
            raise NoMatch()

    def require_next_element(self, element_spec, expected):
        if callable(element_spec):
            try: element = element_spec(self._full_text, self.end)
            except NoMatch: raise self.syntax_error(expected)
            else:
                self.end = element.end
                return element
        else:
            for element_class in element_spec:
                try: element = element_class(self._full_text, self.end)
                except NoMatch: pass
                else:
                    self.end = element.end
                    return element
            expected = ', '.join([cls.__name__ for cls in element_spec])
            raise self.syntax_error(self, 'one of: ' + expected)


class Text(_Element):
    PLAIN = re.compile(r'((?:[^\\\$#]|\\[\$#])+|\$[^!\{a-z0-9_]|\$$|\\\\)(.*)$', re.S + re.I)
    ESCAPED_CHAR = re.compile(r'\\([\\\$#])')

    def parse(self):
        text, = self.identity_match(self.PLAIN)
        def unescape(match):
            return match.group(1)
        self.text = self.ESCAPED_CHAR.sub(unescape, text)

    def evaluate(self, namespace, stream, loader):
        stream.write(self.text)


class IntegerLiteral(_Element):
    INTEGER = re.compile(r'(\d+)(.*)', re.S)

    def parse(self):
        self.value, = self.identity_match(self.INTEGER)
        self.value = int(self.value)

    def calculate(self, namespace):
        return self.value


class StringLiteral(_Element):
    STRING = re.compile(r'"((?:\\["nrbt\\\\]|[^"\n\r"\\])+)"(.*)', re.S)
    ESCAPED_CHAR = re.compile(r'\\([nrbt"\\])')

    def parse(self):
        value, = self.identity_match(self.STRING)
        def unescape(match):
            return {'n': '\n', 'r': '\r', 'b': '\b', 't': '\t', '"': '"', '\\': '\\'}[match.group(1)]
        self.value = self.ESCAPED_CHAR.sub(unescape, value)

    def calculate(self, namespace):
        return self.value


class Value(_Element):
    def parse(self):
        self.expression = self.next_element((SimpleReference, IntegerLiteral, StringLiteral))

    def calculate(self, namespace):
        return self.expression.calculate(namespace)


class NameOrCall(_Element):
    NAME = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)(.*)$', re.S)
    parameters = None

    def parse(self):
        self.name, = self.identity_match(self.NAME)
        try: self.parameters = self.next_element(ParameterList)
        except NoMatch: pass

    def calculate(self, current_object, top_namespace):
        try: result = getattr(current_object, self.name)
        except AttributeError:
            try: result = current_object[self.name]
            except KeyError: result = None
        if result is None:
            return None ## TODO: an explicit 'not found' exception?
        if self.parameters is not None:
            values = [value.calculate(top_namespace) for value in self.parameters.values]
            result = result(*values)
        return result


class SubExpression(_Element):
    DOT = re.compile('\.(.*)', re.S)

    def parse(self):
        self.identity_match(self.DOT)
        self.expression = self.next_element(VariableExpression)

    def calculate(self, current_object, global_namespace):
        return self.expression.calculate(current_object, global_namespace)


class VariableExpression(_Element):
    subexpression = None

    def parse(self):
        self.part = self.next_element(NameOrCall)
        try: self.subexpression = self.next_element(SubExpression)
        except NoMatch: pass

    def calculate(self, namespace, global_namespace=None):
        if global_namespace == None:
            global_namespace = namespace
        value = self.part.calculate(namespace, global_namespace)
        if self.subexpression:
            value = self.subexpression.calculate(value, namespace)
        return value


class ParameterList(_Element):
    START = re.compile(r'\(\s*(.*)$', re.S)
    END = re.compile(r'\s*\)(.*)$', re.S)
    COMMA = re.compile(r'\s*,\s*(.*)$', re.S)

    def parse(self):
        self.values = []
        self.identity_match(self.START)
        try: value = self.next_element(Value)
        except NoMatch:
            pass
        else:
            self.values.append(value)
            while self.optional_match(self.COMMA):
                value = self.require_next_element(Value, 'value')
                self.values.append(value)
        self.require_match(self.END, ')')


class Placeholder(_Element):
    START = re.compile(r'\$(!?)(\{?)(.*)$', re.S)
    CLOSING_BRACE = re.compile(r'\}(.*)$', re.S)

    def parse(self):
        self.silent, self.braces = self.identity_match(self.START)
        self.expression = self.require_next_element(VariableExpression, 'expression')
        if self.braces: self.require_match(self.CLOSING_BRACE, '}')

    def evaluate(self, namespace, stream, loader):
        value = self.expression.calculate(namespace)
        if value is None:
            if self.silent: value = ''
            else: value = self.my_text()
        stream.write(str(value))


class SimpleReference(_Element):
    LEADING_DOLLAR = re.compile('\$(.*)', re.S)

    def parse(self):
        self.identity_match(self.LEADING_DOLLAR)
        self.expression = self.require_next_element(VariableExpression, 'name')
        self.calculate = self.expression.calculate


class Null:
    def evaluate(self, namespace, stream, loader): pass


class Comment(_Element, Null):
    COMMENT = re.compile('#(?:#.*?(?:\n|$)|\*.*?\*#(?:[ \t]*\n)?)(.*)$', re.M + re.S)

    def parse(self):
        self.identity_match(self.COMMENT)


class BinaryOperator(_Element):
    BINARY_OP = re.compile(r'\s*(>=|<=|<|==|!=|>)\s*(.*)$', re.S)
    OPERATORS = {'>' : operator.__gt__, '>=': operator.__ge__,
                 '<' : operator.__lt__, '<=': operator.__le__,
                 '==': operator.__eq__, '!=': operator.__ne__}
    def parse(self):
        op_string, = self.identity_match(self.BINARY_OP)
        self.apply_to = self.OPERATORS[op_string]


class Condition(_Element):
    START = re.compile(r'\(\s*(.*)$', re.S)
    END = re.compile(r'\s*\)(.*)$', re.S)
    binary_operator = None
    value2 = None

    def parse(self):
        self.identity_match(self.START)
        self.value = self.next_element(Value)
        try:
            self.binary_operator = self.next_element(BinaryOperator)
            self.value2 = self.require_next_element(Value, 'value')
        except NoMatch:
            pass
        self.require_match(self.END, ') or >')

    def calculate(self, namespace):
        if self.binary_operator is None:
            return self.value.calculate(namespace)
        else:
            value1, value2 = self.value.calculate(namespace), self.value2.calculate(namespace)
            return self.binary_operator.apply_to(value1, value2)


class End(_Element):
    END = re.compile(r'#end(.*)', re.I + re.S)

    def parse(self):
        self.identity_match(self.END)


class ElseBlock(_Element):
    START = re.compile(r'#else(.*)$', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.block = self.require_next_element(Block, 'block')
        self.evaluate = self.block.evaluate


class ElseifBlock(_Element):
    START = re.compile(r'#elseif\b\s*(.*)$', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.condition = self.require_next_element(Condition, 'condition')
        self.block = self.require_next_element(Block, 'block')
        self.calculate = self.condition.calculate
        self.evaluate = self.block.evaluate


class IfDirective(_Element):
    START = re.compile(r'#if\b\s*(.*)$', re.S + re.I)
    else_block = Null()

    def parse(self):
        self.identity_match(self.START)
        self.condition = self.next_element(Condition)
        self.block = self.next_element(Block)
        self.elseifs = []
        while True:
            try: self.elseifs.append(self.next_element(ElseifBlock))
            except NoMatch: break
        try: self.else_block = self.next_element(ElseBlock)
        except NoMatch: pass
        self.require_next_element(End, '#else, #elseif or #end')

    def evaluate(self, namespace, stream, loader):
        if self.condition.calculate(namespace):
            self.block.evaluate(namespace, stream, loader)
        else:
            for elseif in self.elseifs:
                if elseif.calculate(namespace):
                    elseif.evaluate(namespace, stream, loader)
                    return
            self.else_block.evaluate(namespace, stream, loader)


class Assignment(_Element):
    START = re.compile(r'\s*\(\s*\$([a-z_][a-z0-9_]*)\s*=\s*(.*)$', re.S)
    END = re.compile(r'\s*\)(?:[ \t]*\r?\n)?(.*)$', re.S + re.M)

    def parse(self):
        self.var_name, = self.identity_match(self.START)
        self.value = self.next_element(Value)
        self.require_match(self.END, ')')

    def calculate(self, namespace):
        namespace[self.var_name] = self.value.calculate(namespace)


class MacroDefinition(_Element):
    START = re.compile(r'#macro\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    NAME = re.compile(r'\s*([a-z][a-z_0-9]*)\b(.*)', re.S + re.I)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)
    ARG_NAME = re.compile(r'[ \t]+\$([a-z][a-z_0-9]*)(.*)$', re.S + re.I)
    RESERVED_NAMES = ('if', 'else', 'elseif', 'set', 'macro', 'foreach', 'parse', 'include', 'stop', 'end')
    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.macro_name, = self.require_match(self.NAME, 'macro name')
        if self.macro_name.lower() in self.RESERVED_NAMES:
            raise self.syntax_error('non-reserved name')
        self.arg_names = []
        while True:
            m = self.next_match(self.ARG_NAME)
            if not m: break
            self.arg_names.append(m[0])
        self.require_match(self.CLOSE_PAREN, ') or arg name')
        self.block = self.require_next_element(Block, 'block')
        self.require_next_element(End, 'block')

    def evaluate(self, namespace, stream, loader):
        macro_key = '#' + self.macro_name.lower()
        if macro_key in namespace:
            raise Exception("cannot redefine macro")
        namespace[macro_key] = self

    def execute_macro(self, namespace, stream, arg_value_elements, loader):
        if len(arg_value_elements) != len(self.arg_names):
            raise Exception("expected %d arguments, got %d" % (len(self.arg_names), len(arg_value_elements)))
        macro_namespace = LocalNamespace(namespace)
        for arg_name, arg_value in zip(self.arg_names, arg_value_elements):
            macro_namespace[arg_name] = arg_value.calculate(namespace)
        self.block.evaluate(macro_namespace, stream, loader)


class MacroCall(_Element):
    START = re.compile(r'#([a-z][a-z_0-9]*)\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)
    SPACE = re.compile(r'[ \t]+(.*)$', re.S)

    def parse(self):
        self.macro_name, = self.identity_match(self.START)
        self.macro_name = self.macro_name.lower()
        self.args = []
        if self.macro_name in MacroDefinition.RESERVED_NAMES or self.macro_name.startswith('end'):
            raise NoMatch()
        self.require_match(self.OPEN_PAREN, '(')
        while True:
            try: self.args.append(self.next_element(Value))
            except NoMatch: break
            if not self.optional_match(self.SPACE): break
        self.require_match(self.CLOSE_PAREN, 'argument value or )')

    def evaluate(self, namespace, stream, loader):
        try: macro = namespace['#' + self.macro_name]
        except KeyError: raise Exception('no such macro: ' + self.macro_name)
        macro.execute_macro(namespace, stream, self.args, loader)


class IncludeDirective(_Element):
    START = re.compile(r'#include\b(.*)', re.S + re.I)
    OPEN_PAREN = re.compile(r'[ \t]*\(\s*(.*)$', re.S)
    CLOSE_PAREN = re.compile(r'[ \t]*\)(.*)$', re.S)

    def parse(self):
        self.identity_match(self.START)
        self.require_match(self.OPEN_PAREN, '(')
        self.name = self.require_next_element((StringLiteral, SimpleReference), 'template name')
        self.require_match(self.CLOSE_PAREN, ')')

    def evaluate(self, namespace, stream, loader):
        template = loader.merge_text(self.name.calculate(namespace), stream)


class SetDirective(_Element):
    START = re.compile(r'#set\b(.*)', re.S + re.I)

    def parse(self):
        self.identity_match(self.START)
        self.assignment = self.require_next_element(Assignment, 'assignment')

    def evaluate(self, namespace, stream, loader):
        self.assignment.calculate(namespace)


class ForeachDirective(_Element):
    START = re.compile(r'#foreach\s*\(\s*\$([a-z_][a-z0-9_]*)\s*in\s*(.*)$', re.S + re.I)
    END = re.compile(r'\s*\)(.*)$', re.S)

    def parse(self):
        ## Could be cleaner b/c syntax error if no '('
        self.loop_var_name, = self.identity_match(self.START)
        self.value = self.next_element(Value)
        self.require_match(self.END, ')')
        self.block = self.next_element(Block)
        self.require_next_element(End, '#end')

    def evaluate(self, namespace, stream, loader):
        iterable = self.value.calculate(namespace)
        counter = 1
        for item in iterable:
            namespace = LocalNamespace(namespace)
            namespace['velocityCount'] = counter
            namespace[self.loop_var_name] = item
            self.block.evaluate(namespace, stream, loader)
            counter += 1


class TemplateBody(_Element):
    def parse(self):
        self.block = self.next_element(Block)
        if self.next_text():
            raise self.syntax_error('block element')

    def evaluate(self, namespace, stream, loader):
        namespace = LocalNamespace(namespace)
        self.block.evaluate(namespace, stream, loader)


class Block(_Element):
    def parse(self):
        self.children = []
        while True:
            try: self.children.append(self.next_element((Text, Placeholder, Comment, IfDirective, SetDirective, ForeachDirective, IncludeDirective, MacroDefinition, MacroCall)))
            except NoMatch: break

    def evaluate(self, namespace, stream, loader):
        for child in self.children:
            child.evaluate(namespace, stream, loader)
