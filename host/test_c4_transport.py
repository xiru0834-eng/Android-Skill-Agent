"""Extraction equivalence plus no-model dependency guard."""
import ast,inspect,unittest
from pathlib import Path
import c2_http_transport as transport

class ExtractionTests(unittest.TestCase):
    def test_original_http_framing_ast_unchanged(self):
        original=ast.parse(Path('C:/Users/zz/Documents/ChatGPT/毕设/model-gateway/intent_bridge.py').read_text(encoding='utf-8'))
        new=ast.parse(inspect.getsource(transport))
        for cls,methods in {'ReceiveDeadline':['__init__','readable','readinto','close'],
                            'Handler':['setup','log_message','reply','discard_rejected_input']}.items():
            a=next(n for n in original.body if isinstance(n,ast.ClassDef) and n.name==cls)
            b=next(n for n in new.body if isinstance(n,ast.ClassDef) and n.name==cls)
            for method in methods:
                x=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name==method)
                y=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name==method)
                self.assertEqual(ast.dump(x),ast.dump(y),cls+'.'+method)
    def test_imports_only_framing_dependencies(self):
        tree=ast.parse(inspect.getsource(transport))
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):self.assertTrue(all(a.name in {'io','json','time'} for a in n.names))
            if isinstance(n,ast.ImportFrom):self.assertEqual(n.module,'http.server')

if __name__=='__main__':unittest.main(verbosity=2)
