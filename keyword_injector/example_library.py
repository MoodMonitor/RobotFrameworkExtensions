from robot.libraries.BuiltIn import BuiltIn
from example_library2 import (example_library2_kw_with_no_keyword_error, example_library2_kw_with_keyword_import,
                              example_library2_kw_without_no_keyword_error)

def example_library_kw_with_no_keyword_error():
    BuiltIn().log("example_library_kw_with_no_keyword_error run")
    BuiltIn().run_keyword("example_library2_kw_with_no_keyword_error")


def example_library_kw_without_no_keyword_error():
    BuiltIn().log("example_library_kw_without_no_keyword_error run")
    BuiltIn().run_keyword("example_library2_kw_without_no_keyword_error")

def example_library_kw_with_keyword_import():
    BuiltIn().log("example_library_kw_with_keyword_import run")
    BuiltIn().run_keyword("example_library2_kw_with_keyword_import")