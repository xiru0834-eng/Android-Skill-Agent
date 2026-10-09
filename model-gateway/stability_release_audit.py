"""Release identity/preservation checks. Cancellation endpoint only; no model calls."""
import hashlib
import json
import secrets
import shutil
from pathlib import Path
import urllib.error
import urllib.request
from named_journey_device import prefs
from transfer_run import private
from workflow_experiment import adb,write

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/stability-role-audit-v1'


def audit():
    # The phone experiment saved the input and verified all protected state.
    restored=json.loads((OUT/'phone-saturated/restored.json').read_text(encoding='utf-8'))
    if not all(restored[k] for k in ['reverseRestored','inputRestored','libraryUnchanged',
        'approvedUnchanged','resultUnchanged','oracleUnchanged']) or restored['remoteCalls']!=0:
        raise ValueError('PHONE_PRESERVATION_FAILED')
    workflow=prefs('R5CW134LLBZ');oracle=private('R5CW134LLBZ','edu.sydney.transferlab','workflow-oracle.json')
    token=prefs('R5CW134LLBZ','language_connection')['pairing'];identity=secrets.token_hex(16)
    def cancel(key,body):
        request=urllib.request.Request('http://127.0.0.1:8768/v1/skill-selection-cancellations',
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=3) as reply:return reply.status,json.load(reply)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    correct=(200,dict(request_id=identity,status='cancelled'))
    if cancel(token,dict(request_id=identity))!=correct or cancel(token,dict(request_id=identity))!=correct:
        raise ValueError('DEPLOYED_CANCEL_OR_IDEMPOTENCE_FAILED')
    if cancel('incorrect-pairing',dict(request_id=identity))[0]!=401 or cancel(token,dict(request_id='invalid'))[0]!=400:
        raise ValueError('DEPLOYED_AUTH_OR_VALIDATION_FAILED')
    if prefs('R5CW134LLBZ')!=workflow or private('R5CW134LLBZ','edu.sydney.transferlab','workflow-oracle.json')!=oracle:
        raise ValueError('DEPLOYMENT_CHANGED_PROTECTED_STATE')
    mapping=adb('R5CW134LLBZ','reverse','--list').splitlines()
    if not any(line.split()[-2:]==['tcp:8765','tcp:8768'] for line in mapping):raise ValueError('WRONG_USB_MAPPING')
    session=json.loads((ROOT/'runtime/selector-session/gpt-safe.json').read_text(encoding='utf-8-sig'))
    names=['start_teaching_bridge.py','intent_bridge.py','jev_selection.py','selection_routing.py',
        'catalog_uniqueness.py','contracts.py','skill_selection.py','selection_deadline.py','selection_accuracy.py',
        'deadline_remote.py','compiler.py','win_credentials.py','bridge_launcher_identity.ps1','activate_selector.ps1']
    fingerprint=':'.join(hashlib.sha256((ROOT/'model-gateway'/name).read_bytes()).hexdigest().upper() for name in names)
    if session['selector']!='gpt-safe' or session['port']!=8768 or session['codeFingerprint']!=fingerprint:
        raise ValueError('DEPLOYED_SOURCE_IDENTITY_MISMATCH')
    destination=OUT/'release-source';destination.mkdir(exist_ok=False)
    manifest={}
    for name in names+['entry_phone.py','test_entry_bridge.py','test_entry_roles.py','test_entry_phone_protocol.py','stability_release_audit.py']:
        source=ROOT/'model-gateway'/name;shutil.copy2(source,destination/name)
        manifest[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    package=adb('R5CW134LLBZ','shell','pm','path','edu.sydney.probe').strip()
    if not package.startswith('package:/data/app/') or '\n' in package:raise ValueError('APK_PATH')
    installed=OUT/'installed-unchanged.apk';adb('R5CW134LLBZ','pull',package[len('package:'):],str(installed))
    digest=hashlib.sha256(installed.read_bytes()).hexdigest()
    expected=hashlib.sha256((ROOT/'android-agent-probe/build/manual/demo-probe-entry-hardening.apk').read_bytes()).hexdigest()
    if digest!=expected:raise ValueError('INSTALLED_APK_CHANGED')
    write(OUT/'release-audit.json',dict(passed=True,contractChecks=4,remoteModelCalls=0,
        sourceHashes=manifest,selector='gpt-safe',hostPort=8768,phonePort=8765,pid=session['pid'],
        sessionRequestCap=session['maxCalls'],sourceFingerprintMatches=True,installedAPKUnchanged=True,
        apkSHA256=digest,workflowStateUnchanged=True,targetStateUnchanged=True,credentialsPersisted=False))
    print('PASS release: 4 cancellation/auth checks; new source identity matches; APK/state unchanged; 0 model calls.')


if __name__=='__main__':audit()
