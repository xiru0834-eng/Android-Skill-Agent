"""Explicit learning collection, reusing P2. Evaluator answers are not dependencies."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT.parent/'p2-4-learning-bundle'))
from android_bridge import AndroidBridge
from native_materials import native_bundle
from bundle_contract import make_source,validate_bundle
from bundle_store import BundleStore
from prepare_g1 import save

def collect(host,out):
    out.mkdir(parents=True,exist_ok=False)
    bridge=AndroidBridge(host)
    observations=[]
    try:
        start=bridge.start('edu.sydney.parameterroom')
        if start['status']!='STARTED':raise ValueError('LEARNING_SCOPE_NOT_STARTED')
        for _ in range(3):
            receipt=bridge.observe()
            if receipt.get('status')!='COLLECTED':
                save(out/'capture-failure.json',receipt)
                raise ValueError('OBSERVATION_NOT_CAPTURED')
            observations.append(receipt['observation'])
            time.sleep(.15)
        env={'app_package':'edu.sydney.parameterroom','app_build':str(observations[0]['app_build']),
             'environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        bundle=native_bundle(observations,[],env)
        # Ordinary public capability documentation. No locators, routes or Flow JSON.
        statement={'text':
            'Parameter Room public contract: bedroom_light is the Bedroom light business entity, not the Android host. '
            'SetBrightness sets brightnessPercent using an explicit integer percent from 0 to 100, step 1, unit percent. '
            'This capability does not require power to be changed and does not require a separate Save. '
            'Only brightnessPercent is authorized by a brightness-only request; all other properties must remain unchanged. '
            'A reusable brightness procedure must read current public state, perform the requested supported setting, '
            'and assert the requested actual final brightness. Already-satisfied goals require no business write. '
            'Runtime implements SetBrightness as an idempotent absolute setter: it freshly reads the current value and '
            'skips its business input if that individual call is already satisfied, then verifies the observed value. '
            'A Flow CALL therefore needs no conditional branch to implement this skip. Explicit intermediate calls remain ordered. '
            'This documentation defines business meaning; it is not proof of current UI execution or of full-domain reliability.'}
        bundle['sources'].append(make_source('public.parameterroom.contract','PUBLIC_CAPABILITY_DOCUMENT',statement,
            basis='DOCUMENTATION_STATEMENT',grade='APPROVED_PUBLIC_BUSINESS_CONTRACT',
            limitations=['MAINTAINER_DOCUMENTATION_ASSISTED','NOT_CURRENT_UI_EXECUTION_PROOF']))
        bundle['human_participation'].append({'role':'PUBLIC_CONTRACT_AUTHOR','status':'DOCUMENTATION_ASSISTED',
            'source_ids':['public.parameterroom.contract'],'cost_seconds':None})
        from lab_transport import adb
        metadata=adb(host,'shell','dumpsys','package','edu.sydney.parameterroom').decode()
        if 'versionCode=6 ' not in metadata or 'versionName=0.8-parameter-room' not in metadata:
            raise ValueError('BUILD_RELATION_NOT_CONFIRMED')
        bundle['sources'].append(make_source('public.current.build','PUBLIC_PACKAGE_METADATA',
            {'text':'Current Android package edu.sydney.parameterroom has versionCode 6 and versionName 0.8-parameter-room. '
                    'This fresh runtime package metadata confirms the build/version relation for these observations.'},
            basis='DOCUMENTATION_STATEMENT',grade='CURRENT_RUNTIME_METADATA_CHECK',
            limitations=['HOST_PACKAGE_METADATA_NOT_BUSINESS_ORACLE']))
        validate_bundle(bundle)
        with BundleStore(out/'memory.sqlite',create=True) as store:store.append(bundle,expected_revision=0)
        save(out/'learning-bundle.json',bundle)
        return bundle
    finally:
        if bridge.scope_id:
            try:bridge.stop()
            except Exception:bridge.cancel()
        save(out/'native-receipts.json',bridge.calls)
if __name__=='__main__':
    b=collect(sys.argv[1],Path(sys.argv[2]));print(json.dumps({'pages':len(b['pages']),'sources':len(b['sources']),'model_calls':0}))
