#!/usr/bin/env python

from unittest import TestCase, main
import airspeed


class TemplateTestCase(TestCase):

    def test_parser_returns_input_when_there_is_nothing_to_substitute(self):
        template = airspeed.Template("<html></html>")
        self.assertEquals("<html></html>", template.merge({}))

    def test_parser_substitutes_string_added_to_the_context(self):
        template = airspeed.Template("Hello $name")
        self.assertEquals("Hello Chris", template.merge({"name": "Chris"}))

    def test_dollar_left_untouched(self):
        template = airspeed.Template("Hello $ ")
        self.assertEquals("Hello $ ", template.merge({}))
        template = airspeed.Template("Hello $")
        self.assertEquals("Hello $", template.merge({}))

    def test_unmatched_name_does_not_get_substituted(self):
        template = airspeed.Template("Hello $name")
        self.assertEquals("Hello $name", template.merge({}))

    def test_silent_substitution_for_unmatched_values(self):
        template = airspeed.Template("Hello $!name")
        self.assertEquals("Hello world", template.merge({"name": "world"}))
        self.assertEquals("Hello ", template.merge({}))

    def test_embed_substitution_value_in_braces_gets_handled(self):
        template = airspeed.Template("Hello ${name}.")
        self.assertEquals("Hello World.", template.merge({"name": "World"}))

    def test_unmatched_braces_raises_exception(self):
        template = airspeed.Template("Hello ${name.")
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_unmatched_trailing_brace_preserved(self):
        template = airspeed.Template("Hello $name}.")
        self.assertEquals("Hello World}.", template.merge({"name": "World"}))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        self.assertEquals("Hello Chris", template.merge({"name": o}))

    def test_can_return_value_from_an_attribute_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name")
        class MyObj: pass
        o = MyObj()
        o.first_name = 'Chris'
        self.assertEquals("Hello Chris", template.merge({"name": o}))

    def test_can_return_value_from_a_method_of_a_context_object(self):
        template = airspeed.Template("Hello $name.first_name()")
        class MyObj:
            def first_name(self): return "Chris"
        self.assertEquals("Hello Chris", template.merge({"name": MyObj()}))

    def test_when_if_statement_resolves_to_true_the_content_is_returned(self):
        template = airspeed.Template("Hello #if ($name)your name is ${name}#end Good to see you")
        self.assertEquals("Hello your name is Steve Good to see you", template.merge({"name": "Steve"}))

    def test_when_if_statement_resolves_to_false_the_content_is_skipped(self):
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}#end Good to see you")
        self.assertEquals("Hello  Good to see you", template.merge({"name": "Steve", "show_greeting": False}))

    def test_when_if_statement_is_nested_inside_a_successful_enclosing_if_it_gets_evaluated(self):
        template = airspeed.Template("Hello #if ($show_greeting)your name is ${name}.#if ($is_birthday) Happy Birthday.#end#end Good to see you")
        namespace = {"name": "Steve", "show_greeting": False}
        self.assertEquals("Hello  Good to see you", template.merge(namespace))
        namespace["show_greeting"] = True
        self.assertEquals("Hello your name is Steve. Good to see you", template.merge(namespace))
        namespace["is_birthday"] = True
        self.assertEquals("Hello your name is Steve. Happy Birthday. Good to see you", template.merge(namespace))

    def test_new_lines_in_templates_are_permitted(self):
        template = airspeed.Template("hello #if ($show_greeting)${name}.\n#if($is_birthday)Happy Birthday\n#end.\n#endOff out later?")
        namespace = {"name": "Steve", "show_greeting": True, "is_birthday": True}
        self.assertEquals("hello Steve.\nHappy Birthday\n.\nOff out later?", template.merge(namespace))

    def test_foreach_with_plain_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello you. #end")
        self.assertEquals("Hello you. Hello you. ", template.merge({"names": ["Chris", "Steve"]}))

    def test_foreach_skipped_when_nested_in_a_failing_if(self):
        template = airspeed.Template("#if ($false_value)#foreach ($name in $names)Hello you. #end#end")
        self.assertEquals("", template.merge({"false_value": False, "names": ["Chris", "Steve"]}))

    def test_foreach_with_expression_content_loops_correctly(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $you. #end")
        self.assertEquals("Hello You. Hello You. ", template.merge({"you": "You", "names": ["Chris", "Steve"]}))

    def test_foreach_makes_loop_variable_accessible(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end")
        self.assertEquals("Hello Chris. Hello Steve. ", template.merge({"names": ["Chris", "Steve"]}))

    def test_loop_variable_not_accessible_after_loop(self):
        template = airspeed.Template("#foreach ($name in $names)Hello $name. #end$name")
        self.assertEquals("Hello Chris. Hello Steve. $name", template.merge({"names": ["Chris", "Steve"]}))

    def test_loop_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)$word to#foreach ($word in $names) $word#end. #end")
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEquals("Hello to Chris Steve. Goodbye to Chris Steve. ", template.merge(namespace))

    def test_loop_counter_variable_available_in_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)$velocityCount,#end")
        namespace = {"greetings": ["Hello", "Goodbye"]}
        self.assertEquals("1,2,", template.merge(namespace))

    def test_loop_counter_variables_do_not_clash_in_nested_loops(self):
        template = airspeed.Template("#foreach ($word in $greetings)Outer $velocityCount#foreach ($word in $names), inner $velocityCount#end. #end")
        namespace = {"greetings": ["Hello", "Goodbye"], "names": ["Chris", "Steve"]}
        self.assertEquals("Outer 1, inner 1, inner 2. Outer 2, inner 1, inner 2. ", template.merge(namespace))

    def test_can_use_an_integer_variable_defined_in_template(self):
        template = airspeed.Template("#set ($value = 10)$value")
        self.assertEquals("10", template.merge({}))

    def test_passed_in_namespace_not_modified_by_set(self):
        template = airspeed.Template("#set ($value = 10)$value")
        namespace = {}
        template.merge(namespace)
        self.assertEquals({}, namespace)

    def test_can_use_a_string_variable_defined_in_template(self):
        template = airspeed.Template('#set ($value = "Steve")$value')
        self.assertEquals("Steve", template.merge({}))

    def test_single_line_comments_skipped(self):
        template = airspeed.Template('## comment\nStuff\nMore stuff## more comments $blah')
        self.assertEquals("Stuff\nMore stuff", template.merge({}))

    def test_multi_line_comments_skipped(self):
        template = airspeed.Template('Stuff#*\n more comments *#\n and more stuff')
        self.assertEquals("Stuff and more stuff", template.merge({}))

    def test_merge_to_stream(self):
        template = airspeed.Template('Hello $name!')
        from cStringIO import StringIO
        output = StringIO()
        template.merge_to({"name": "Chris"}, output)
        self.assertEquals('Hello Chris!', output.getvalue())

    def test_string_literal_can_contain_embedded_escaped_quotes(self):
        template = airspeed.Template('#set ($name = "\\"batman\\"")$name')
        self.assertEquals('"batman"', template.merge({}))

    def test_string_literal_can_contain_embedded_escaped_newlines(self):
        template = airspeed.Template('#set ($name = "\\\\batman\\nand robin")$name')
        self.assertEquals('\\batman\nand robin', template.merge({}))

    def test_else_block_evaluated_when_if_expression_false(self):
        template = airspeed.Template('#if ($value) true #else false #end')
        self.assertEquals(" false ", template.merge({}))

    def test_too_many_end_clauses_trigger_error(self):
        template = airspeed.Template('#if (1)true!#end #end ')
        self.assertRaises(airspeed.TemplateSyntaxError, template.merge, {})

    def test_can_call_function_with_one_parameter(self):
        def squared(number):
            return number * number
        template = airspeed.Template('$squared(8)')
        self.assertEquals("64", template.merge(locals()))
        some_var = 6
        template = airspeed.Template('$squared($some_var)')
        self.assertEquals("36", template.merge(locals()))
        template = airspeed.Template('$squared($squared($some_var))')
        self.assertEquals("1296", template.merge(locals()))

    def test_can_call_function_with_one_parameter(self):
        def multiply(number1, number2):
            return number1 * number2
        template = airspeed.Template('$multiply(2, 4)')
        self.assertEquals("8", template.merge(locals()))
        template = airspeed.Template('$multiply( 2 , 4 )')
        self.assertEquals("8", template.merge(locals()))
        value1, value2 = 4, 12
        template = airspeed.Template('$multiply($value1,$value2)')
        self.assertEquals("48", template.merge(locals()))

#
# TODO:
#
#  Escaped characters in string literals
#  Directives inside string literals
#  #elseif
#  Parameterised calls
#  #parse, #include
#  #macro
#  map literals
#  Escaped $, #
#  Sub-object assignment:  #set( $customer.Behavior = $primate )
#  Q. What is scope of #set ($customer.Name = 'john')  ???
#


if __name__ == '__main__':
    reload(airspeed)
    try: main()
    except SystemExit: pass
