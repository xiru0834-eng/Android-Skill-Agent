"""Evidence/build setup only. Captures full private pre-test snapshots before installation."""
import hashlib,json,subprocess,sys
from pathlib import Path
from lab_transport import adb,HOSTS
ROOT=Path(__file__).parent
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def snapshot():
    target=ROOT/'private/before-v93'
    target.mkdir(parents=True,exist_ok=False)
    public={}
    for host in sorted(HOSTS):
        d=target/host;d.mkdir()
        for pkg in ['edu.sydney.probe','edu.sydney.parameterroom']:
            data=adb(host,'shell','run-as',pkg,'tar','-cf','-','files','shared_prefs')
            (d/(pkg+'.tar')).write_bytes(data)
            apk_path=adb(host,'shell','pm','path',pkg).decode().strip().split(':',1)[1]
            adb(host,'pull',apk_path,str(d/(pkg+'.apk')))
        settings={k:adb(host,'shell','settings','get','secure',k).decode().strip() for k in ['enabled_accessibility_services','accessibility_enabled']}
        save(d/'settings.json',settings)
        public[host]={'apk_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*.apk')},
                      'tar_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in d.glob('*.tar')},'snapshot_private':True}
    source={str(p.relative_to(ROOT/'native')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'native/app/src/main').rglob('*') if p.is_file()}
    save(ROOT/'evidence/preinstall-freeze.json',{'snapshots':public,'source':source})
def plans():
    sys.path.insert(0,'D:/Codex-deliveries/smarthome-ui-polish/p1-3-flow-compiler')
    from fixtures import bundle
    from compiler import compile_flow
    for host in sorted(HOSTS):
        flow,pkg,task=bundle('SetBrightness',80)
        target={'entity_input':'entity','property':'brightnessPercent'}
        flow['steps']=[{'id':'read_before','op':'read','target':target},flow['steps'][0],
                       {'id':'assert_after','op':'assert','predicate':flow['goals'][0]}]
        task['host_device_id']='host.'+host.replace('-','_').lower();task['budget']={'duration_ms':8000,'max_actions':4,'max_model_calls':0}
        plan=compile_flow(flow,pkg,task,None).to_dict()
        save(ROOT/'evidence'/host/'g1-plan.json',plan)
        save(ROOT/'evidence'/host/'g1-sources.json',{'flow':flow,'package':pkg,'task':task,'provenance':'TEST_FIXTURE'})
if __name__=='__main__':
    if sys.argv[1]=='snapshot':snapshot()
    elif sys.argv[1]=='plans':plans()
