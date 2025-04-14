from robot.running.librarykeyword import LibraryKeyword
from robot.running.arguments import PythonArgumentParser
from robot.libraries.BuiltIn import BuiltIn


class InjectedKeyword(LibraryKeyword):

    def __init__(self, owner, name, method=None):
        super().__init__(owner=owner, name=name, args=PythonArgumentParser().parse(method))
        self._method = method

    @property
    def method(self):
        return self._method

    def copy(self, **attributes):
        return InjectedKeyword(owner=self.owner, name=self.name, method=self._method)


def inject_keyword_to_robot_namespace_and_run(function, *args):
    context = BuiltIn()._context
    namespace = context.namespace
    kw_store = namespace._kw_store
    keyword = InjectedKeyword(name=function.__name__, owner=kw_store.libraries["BuiltIn"], method=function)
    kw_store.libraries["BuiltIn"].keywords.append(keyword)
    kw_store.libraries["BuiltIn"].keyword_finder.cache = None  # need to clear cache, look on keywordfinder.py
    return BuiltIn().run_keyword("BuiltIn.{}".format(function.__name__), *args)