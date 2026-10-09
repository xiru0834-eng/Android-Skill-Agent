"""Immutable final candidate/test freeze; never overwrites old sealed evidence."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
from prepare_g1 import save
ROOT=Path(__file__).parent
OUT=ROOT/'evidence/flow-deadline-repair/r1/freeze-v97-confirmation-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    OUT.mkdir(parents=True,exist_ok=False);files={}
    with zipfile.ZipFile(ROOT/'private/flow-deadline-repair-r1/source-v97-confirmation-r2.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob('*')):
            if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ('private','evidence','.git','__pycache__','build')):
                files[str(p.relative_to(ROOT))]=sha(p);z.write(p,str(p.relative_to(ROOT)))
    core={}
    for n in ('PortableSkillRuntime','AccessibilityBindingResolver','AccessibilityRangeExecutor','PortableSkillCodec'):
        p=ROOT/'native/app/src/main/java/edu/sydney/probe'/(n+'.java')
        old=ROOT.parent/'native-learning-candidate-v92/app/src/main/java/edu/sydney/probe'/(n+'.java')
        core[n]={'current':sha(p),'original_v92':sha(old),'unchanged':sha(p)==sha(old)}
    apk=ROOT/'native/build/manual/flow-probe-v97-viewport.apk'
    import flow_bridge
    external={}
    dependency_roots=[Path('C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')]+[ROOT.parent/n for n in ('p1-2-flow-contracts','p1-3-flow-compiler','p1-4-flow-store-adapter','p2-1-learning-scope','p2-2-page-observation','p2-3-interaction-trace','p2-4-learning-bundle','p3-1-draft-generator','p3-2-flow-abstraction','p3-3-layered-validation','p3-4-knowledge-publication','p5-1-knowledge-export','p5-2-knowledge-import')]
    for folder in dependency_roots:
        for p in sorted(folder.rglob('*.py')):
            if not any(x in p.relative_to(folder).parts for x in ('private','evidence','.git','__pycache__','build','.venv')):external[str(p)]=sha(p)
    capsules={str(p):sha(p) for p in (ROOT/'evidence/g2-native-reviewed-knowledge-r2.json',ROOT/'evidence/g4-real-package-transfer-r1/target-native-knowledge.json')}
    save(OUT/'freeze.json',{'source':files,'source_digest':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        'external_python_sources':external,'published_capsules':capsules,'model':flow_bridge.MODEL,
        'prompt_sha256':hashlib.sha256(flow_bridge.PROMPT.encode()).hexdigest(),'model_configuration':{'temperature':0,'reasoning':'none','max_output_tokens':512},
        'repair_protocol_sha256':sha(Path('C:/Users/zz/Downloads/emulator_flow_timeout_repair_prompt.md')),
        'current_run_snapshots':{h:sha(ROOT/'private/flow-deadline-repair-r1'/h/'snapshot.json') for h in ('emulator-5556','R5CW134LLBZ')},
        'apk':str(apk),'apk_sha256':sha(apk),'original_core':core,'plan':{'baseline_repeats':3,'E1_E2_final_emulator_repeats':3,
        'dual_G1':11,'dual_real_NL':8,'refresh_validation':8,'whole_native_budget_ms':8000,'model_max_attempts':32,'model_max_usd':1,
        'model_retries':0,'score':'ALL_PREDECLARED_EXPECTED_BEHAVIOR_REQUIRED'},'flow_hash':'ec11686ff6cf9874fb71d76fdb4ae492488bf03bac2d3b62e1ae5a707d434203'})
    (OUT/'git-diff.patch').write_bytes(subprocess.run(['git','diff','--binary'],cwd=ROOT,capture_output=True,check=True).stdout)
    if not all(x['unchanged'] for x in core.values()):raise ValueError('ORIGINAL_CORE_CHANGED')
    print('FROZEN',sha(apk),len(files),flush=True)
if __name__=='__main__':run()
