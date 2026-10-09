"""Explicit lab setup; keeps all other enabled services and verifies real service binding."""
import json,time,uuid
from pathlib import Path
from lab_transport import adb
ROOT=Path(__file__).parent
SERVICE='edu.sydney.probe/edu.sydney.probe.ProbeService'
def health(host):
    rid=uuid.uuid4().hex
    adb(host,'shell','am','broadcast','--receiver-foreground','-a','edu.sydney.probe.FLOW_AUDIT','-n','edu.sydney.probe/.FlowAuditReceiver','--es','request_id',rid,'--es','operation','status')
    for _ in range(10):
        try:return json.loads(adb(host,'shell','run-as','edu.sydney.probe','cat','files/flow-audit-'+rid+'.json'))
        except (RuntimeError,json.JSONDecodeError):time.sleep(.1)
    return {'final_status':'HEALTH_TRANSPORT_TIMEOUT'}
def install(host,apk):
    original=json.loads((ROOT/'private/before-v93'/host/'settings.json').read_text())
    current=adb(host,'shell','settings','get','secure','enabled_accessibility_services').decode().strip()
    services=[s for s in current.split(':') if s and s!='null']
    if SERVICE not in services:
        if SERVICE not in original['enabled_accessibility_services'].split(':'):raise RuntimeError('NO_PRIOR_LAB_SERVICE_PERMISSION')
        services.append(SERVICE)
    enabled=':'.join(services)
    result=adb(host,'install','-r',str(apk),timeout=60).decode();print(host,result.strip(),flush=True)
    if 'Success' not in result:raise RuntimeError('INSTALL_NOT_CONFIRMED')
    # Only the test-owned Probe is restarted. Keep CURRENT unrelated services,
    # rather than overwriting them with an older snapshot.
    adb(host,'shell','am','force-stop','edu.sydney.probe')
    others=':'.join(s for s in services if s!=SERVICE)
    adb(host,'shell','settings','put','secure','enabled_accessibility_services',others or 'null')
    # Wait for the actual unbound state, not a fixed sleep between two settings writes.
    until=time.monotonic()+10
    while time.monotonic()<until:
        text=adb(host,'shell','dumpsys','accessibility').decode()
        if 'edu.sydney.probe/' not in text.split('Bound services:',1)[-1].split('Enabled services:',1)[0]:break
        time.sleep(.15)
    adb(host,'shell','settings','put','secure','enabled_accessibility_services',enabled)
    # Do not launch while its old service registration is being removed: that
    # creates an avoidable bind/unbind race during lab APK replacement.
    adb(host,'shell','am','start','-f','0x14000000','-n','edu.sydney.probe/.MainActivity')
    until=time.monotonic()+20
    ready_count=0
    while time.monotonic()<until:
        r=health(host)
        ready_count=ready_count+1 if r.get('final_status')=='READY' else 0
        if ready_count>=3:return r
        time.sleep(.2)
    raise RuntimeError('SERVICE_BINDING_NOT_READY')
if __name__=='__main__':
    import sys
    from prepare_g1 import save
    apk=Path(sys.argv[2]);r=install(sys.argv[1],apk);save(ROOT/'evidence'/('installed-'+sys.argv[1]+'-'+apk.stem+'.json'),r);print('ACTUAL_SERVICE_READY',flush=True)
