"""Capture an actual candidate build, including its exit status and raw diagnostics."""
import hashlib,subprocess,sys
from pathlib import Path
from prepare_g1 import save
ROOT=Path(__file__).parent
label=sys.argv[1];artifact=sys.argv[2]
out=ROOT/'evidence/flow-deadline-repair/r2/build'/label
out.mkdir(parents=True,exist_ok=False)
cmd=['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','native/build-offline.ps1','-ArtifactName',artifact]
result=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=300)
raw=result.stdout+b'\n'+result.stderr;(out/'build.log').write_bytes(raw)
apk=ROOT/'native/build/manual'/artifact
save(out/'result.json',{'command':cmd,'exit_code':result.returncode,'passed':result.returncode==0,
     'log_sha256':hashlib.sha256(raw).hexdigest(),'apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest() if apk.exists() else None})
print('BUILD',label,result.returncode,flush=True)
sys.exit(result.returncode)
