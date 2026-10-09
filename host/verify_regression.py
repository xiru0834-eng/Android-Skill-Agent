"""Reproducible local regression ledger. No models, Android commands or business inputs."""
import hashlib,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).parent

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    jobs=[('wireup',ROOT,[sys.executable,'-m','unittest','test_product_wireup','test_wireup','-v']),
        ('native-core',ROOT,['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','native/test-core.ps1'])]
    for name in ('p1-3-flow-compiler','p2-4-learning-bundle','p3-4-knowledge-publication','p5-2-knowledge-import'):
        jobs.append((name,ROOT.parent/name,[sys.executable,'-m','unittest','discover','-p','test*.py','-v']))
    rows=[];env=dict(os.environ);env.pop('OPENAI_API_KEY',None)
    for name,cwd,cmd in jobs:
        r=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=180)
        # Preserve raw output and digest. Logs are test channel, not task evidence.
        raw=r.stdout+b'\n'+r.stderr;(out/(name+'.log')).write_bytes(raw)
        text=raw.decode('utf-8',errors='replace');match=re.search(r'Ran (\d+) tests?',text)
        count=int(match.group(1)) if match else len(list((ROOT/'native/tests/edu/sydney/probe').glob('*Test.java'))) if name=='native-core' else None
        row={'name':name,'command':cmd,'cwd':str(cwd),'exit_code':r.returncode,'passed':r.returncode==0,
            'test_count':count,'channel':'PURE_LOGIC_OR_CONTRACT_REGRESSION','actual_ui_tasks':0,'model_calls':0,'log_sha256':hashlib.sha256(raw).hexdigest()}
        rows.append(row);print(name,r.returncode,count,flush=True)
    (out/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return all(r['passed'] for r in rows)
if __name__=='__main__':sys.exit(0 if run(Path(sys.argv[1])) else 1)
