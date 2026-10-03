"""Run original normalization and graph controls without local research files."""
from pathlib import Path
import importlib,os,sys,tempfile,json,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

def load_tests(loader,tests,pattern):
    workspace=tempfile.TemporaryDirectory()
    root=Path(workspace.name)
    (root/'protocol').mkdir()
    (root/'protocol/runtime_paths.json').write_text(json.dumps({'jdk':str(root/'jdk'),'m3':str(root/'m3'),'m4':str(root/'m4')}),encoding='utf-8')
    old=os.environ.get('MAVENTWIN_WORKSPACE')
    os.environ['MAVENTWIN_WORKSPACE']=str(root)
    module=importlib.import_module('test_differential')
    class ConfiguredSuite(unittest.TestSuite):
        def run(self,result,debug=False):
            try:return super().run(result,debug)
            finally:
                if old is None:os.environ.pop('MAVENTWIN_WORKSPACE',None)
                else:os.environ['MAVENTWIN_WORKSPACE']=old
                workspace.cleanup()
    return ConfiguredSuite(loader.loadTestsFromModule(module))
