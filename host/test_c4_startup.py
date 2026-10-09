"""Fresh-process entry-point tests; no ADB and no external model calls."""
import subprocess,sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class StartupTests(unittest.TestCase):
    def check_start(self,code):
        r=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr.decode('utf-8',errors='replace'))
    def test_learning_cold(self):self.check_start('import c2_bridge')
    def test_usage_cold(self):self.check_start('import c2_usage_bridge')
    def test_validation_then_learning(self):self.check_start('import c2_validation; import c2_bridge')
    def test_learning_then_validation(self):self.check_start('import c2_bridge; import c2_validation')
    def test_learning_does_not_import_old_model_gateway(self):
        self.check_start("import c2_bridge,sys; assert 'intent_bridge' not in sys.modules; assert 'compiler' not in sys.modules or 'p1-3-flow-compiler' in sys.modules['compiler'].__file__")

if __name__=='__main__':unittest.main(verbosity=2)
