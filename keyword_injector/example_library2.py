from robot.libraries.BuiltIn import BuiltIn
from example_library3 import example_library3_kw
from keyword_injector import inject_keyword_to_robot_namespace_and_run


def example_library2_kw_with_no_keyword_error():
    BuiltIn().log("example_library2_kw_with_no_keyword_error run")
    BuiltIn().run_keyword("example_library3_kw")

def example_library2_kw_without_no_keyword_error():
    BuiltIn().log("example_library2_kw_without_no_keyword_error run")
    inject_keyword_to_robot_namespace_and_run(example_library3_kw)

def example_library2_kw_with_keyword_import():
    BuiltIn().log("example_library2_kw_with_keyword_import run")
    BuiltIn().import_library("example_library3")
    BuiltIn().run_keyword("example_library3.example_library3_kw")
