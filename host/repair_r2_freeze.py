"""Freeze each actual continuation candidate; preserve every older batch."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
from prepare_g1 import save
import flow_bridge

ROOT=Path(__file__).parent
RUN=ROOT/'evidence/flow-deadline-repair/r2'
PRIVATE=ROOT/'private/flow-deadline-repair-r2'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def run(label='v102',artifact='flow-probe-v102-final-boundary.apk'):
    out=RUN/('freeze-'+label);out.mkdir(parents=True,exist_ok=False)
    files={}
    with zipfile.ZipFile(PRIVATE/('source-'+label+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(ROOT.rglob('*')):
            if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ('private','evidence','.git','__pycache__','build')):
                name=str(p.relative_to(ROOT));files[name]=sha(p);archive.write(p,name)
    core={}
    for name in ('PortableSkillRuntime','AccessibilityBindingResolver','AccessibilityRangeExecutor','PortableSkillCodec'):
        current=ROOT/'native/app/src/main/java/edu/sydney/probe'/(name+'.java')
        original=ROOT.parent/'native-learning-candidate-v92/app/src/main/java/edu/sydney/probe'/(name+'.java')
        core[name]={'current':sha(current),'original_v92':sha(original),'unchanged':sha(current)==sha(original)}
    dependency_roots=[Path('C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')]+[ROOT.parent/n for n in
        ('p1-2-flow-contracts','p1-3-flow-compiler','p1-4-flow-store-adapter','p2-1-learning-scope',
         'p2-2-page-observation','p2-3-interaction-trace','p2-4-learning-bundle','p3-1-draft-generator',
         'p3-2-flow-abstraction','p3-3-layered-validation','p3-4-knowledge-publication',
         'p5-1-knowledge-export','p5-2-knowledge-import')]
    external={str(p):sha(p) for folder in dependency_roots for p in sorted(folder.rglob('*.py'))
              if not any(x in p.relative_to(folder).parts for x in ('private','evidence','.git','__pycache__','build','.venv'))}
    apk=ROOT/'native/build/manual'/artifact
    capsules=[ROOT/'evidence/g2-native-reviewed-knowledge-r2.json',ROOT/'evidence/g4-real-package-transfer-r1/target-native-knowledge.json']
    save(out/'freeze.json',{'source':files,'external_python_sources':external,
        'source_digest':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        'apk':str(apk),'apk_sha256':sha(apk),'original_core':core,
        'published_capsules':{str(p):sha(p) for p in capsules},
        'snapshots':{h:sha(PRIVATE/h/'snapshot.json') for h in ('emulator-5556','R5CW134LLBZ')},
        'model':flow_bridge.MODEL,'prompt_sha256':hashlib.sha256(flow_bridge.PROMPT.encode()).hexdigest(),
        'model_configuration':{'temperature':0,'reasoning':'none','max_output_tokens':512,'automatic_retries':0},
        'test_plan':{'dual_structured_diagnostic':12,'dual_g1':22,'dual_cancel':4,'candidate_validation':8,
             'dual_real_nl':16,'dual_real_E1_E2_extra_repeats':8,'E1_E2_repeats_each_host':3,
             'model_max_attempts':32,'estimated_usd_cap':1,'native_total_deadline_ms':8000,
             'score':'ALL_PREDECLARED_EXPECTED_BEHAVIOR_REQUIRED'},
        'flow_hash':'ec11686ff6cf9874fb71d76fdb4ae492488bf03bac2d3b62e1ae5a707d434203'})
    (out/'git-diff.patch').write_bytes(subprocess.run(['git','diff','--binary'],cwd=ROOT,capture_output=True,check=True).stdout)
    if not all(c['unchanged'] for c in core.values()):raise ValueError('ORIGINAL_CORE_CHANGED')
    print('FROZEN',sha(apk),len(files),flush=True)

if __name__=='__main__': run()
