"""Archive only the H2 measurement amendment, separate from frozen APKs."""
import hashlib
import argparse
import shutil
from pathlib import Path
from workflow_experiment import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--version',choices=['H2','H3','H3.1'],default='H2');version=p.parse_args().version
    out=Path('evaluation/teach-once/harness-'+version.lower());out.mkdir(exist_ok=False)
    names=['model-gateway/'+n for n in ('transfer_run.py','transfer_terminal_wait.py','workflow_capture.py','transfer_resume.py','test_transfer_terminal_wait.py','test_transfer_resume.py')]
    names.append('tasks/transfer-harness-timing-amendment.md');hashes={}
    if version.startswith('H3'):names.extend(['model-gateway/transfer_input_ready.py','model-gateway/test_transfer_input_ready.py','tasks/transfer-harness-input-ready-amendment.md'])
    for name in names:
        source=Path(name);dest=out/'files'/source;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    write(out/'manifest.json',dict(harnessVersion=version,sourceFiles=hashes,executorUnchanged=True,taskBudgetMs=30000,
         note='Test-operator amendment only. Earlier failures remain in their original denominators.'))
    print(version+' source snapshot saved; no APK or primary scoring change')


if __name__=='__main__':main()
