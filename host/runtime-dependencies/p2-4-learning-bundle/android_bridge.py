"""Explicit Android collection controller, kept OUT of the four stored-material queries.
No oracle, test-state, input coordinates, business writes, network, or paid model capability.
"""
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

ADB=Path('D:/python_code/closed-loop-gui-agent/tools/android-sdk/platform-tools/adb.exe')
SERIALS={'R5CW134LLBZ','emulator-5556'}


class AndroidBridge:
    def __init__(self,serial):
        if serial not in SERIALS:raise ValueError('UNKNOWN_TEST_HOST')
        self.serial=serial;self.scope_id=None;self.calls=[]

    def _adb(self,*args):
        completed=subprocess.run([str(ADB),'-s',self.serial,*args],capture_output=True,timeout=15)
        if completed.returncode:raise RuntimeError('ANDROID_TRANSPORT_ERROR')
        return completed.stdout.decode('utf-8')

    def request(self,operation,**values):
        if operation not in {'start','capture','click','events','stop','cancel'}:raise ValueError('INVALID_OPERATION')
        rid=uuid.uuid4().hex
        params={'request_id':rid,'operation':operation,'scope_id':self.scope_id,**values}
        allowed={'request_id','operation','scope_id','app_package','observation_id','node_local_id'}
        if set(params)-allowed:raise ValueError('INVALID_FIELD')
        for name,value in params.items():
            if name=='app_package':
                if value not in {'edu.sydney.parameterroom','edu.sydney.transferlab'}:raise ValueError('UNAUTHORIZED_APP')
            elif name in {'scope_id','observation_id','request_id'}:
                if type(value) is not str or not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('INVALID_ID')
            elif name=='node_local_id' and (type(value) is not str or not re.fullmatch('n[0-9]{1,4}',value)):
                raise ValueError('INVALID_NODE_ID')
        args=['shell','am','broadcast','--receiver-foreground','-a','edu.sydney.probe.LEARNING_AUDIT',
              '-n','edu.sydney.probe/.LearningAuditReceiver']
        for name,value in params.items():args.extend(['--es',name,value])
        start=time.monotonic();self._adb(*args)
        receipt=None
        while time.monotonic()-start<8:
            try:
                raw=self._adb('shell','run-as','edu.sydney.probe','cat','files/learning-audit.json')
                if len(raw.encode('utf-8'))>2*1024*1024:raise RuntimeError('RECEIPT_SIZE_LIMIT')
                value=json.loads(raw)
                if value.get('request_id')==rid:receipt=value;break
            except json.JSONDecodeError:pass
            time.sleep(.1)
        if receipt is None:raise RuntimeError('MISSING_NATIVE_RECEIPT')
        receipt['host_transport_label']=self.serial
        receipt['transport_latency_ms']=round((time.monotonic()-start)*1000,3)
        self.calls.append(receipt)
        return receipt

    def start(self,pkg):
        self.scope_id=uuid.uuid4().hex
        return self.request('start',app_package=pkg)

    def observe(self):return self.request('capture')
    def click(self,observation,node):
        return self.request('click',observation_id=observation['observation_id'],node_local_id=node['node_local_id'])
    def events(self):return self.request('events')
    def stop(self):return self.request('stop')
    def cancel(self):return self.request('cancel')
