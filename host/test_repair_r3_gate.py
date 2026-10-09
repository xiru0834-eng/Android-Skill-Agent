"""Offline subprocess fault injection. No ADB, model, or product imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from repair_r3_gate import Batch, GateClosed


FAKE = r'''
import os, json, hashlib, time, sys, subprocess
from pathlib import Path
d=Path(os.environ['R3_COMMAND_DIR']); mode=sys.argv[1]
if mode=='hang': time.sleep(5)
if mode=='child':
 p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'])
 marker=d/'child.pid.tmp'; marker.write_text(str(p.pid)); marker.replace(d/'child.pid'); time.sleep(10)
if mode=='nonzero': sys.exit(7)
if mode=='missing': sys.exit(0)
audit=d/'audit.json'; audit.write_text('{"events":[]}', encoding='utf-8')
r={'batch_id':os.environ['R3_BATCH_ID'], 'command_id':os.environ['R3_COMMAND_ID'],
   'candidate_hash':os.environ['R3_CANDIDATE_HASH'], 'verdict':'PASS',
   'safety':{k:False for k in ['wrong_action','false_success','prohibited_side_effect','post_cancel_dispatch']},
   'audit':{'path':'audit.json','sha256':hashlib.sha256(audit.read_bytes()).hexdigest()}}
if mode=='badjson': (d/'receipt.json').write_text('{',encoding='utf-8'); sys.exit(0)
if mode=='old': r['batch_id']='old'
if mode=='hash': r['candidate_hash']='0'*64
if mode=='unsafe': r['safety']['false_success']=True
if mode=='safety_stop': r['verdict']='SAFETY_STOP'
if mode=='noaudit': audit.unlink()
if mode=='corrupt': audit.write_text('bad')
if mode=='path': r['audit']['path']='../audit.json'
if mode=='types': r['safety']['wrong_action']=0
if mode=='safety_missing': del r['safety']['wrong_action']
if mode=='duplicates': (d/'receipt.json').write_text('{"verdict":"PASS","verdict":"PASS"}'); sys.exit(0)
if mode=='refusal': r['verdict']='EXPECTED_REFUSAL'
if mode=='timeout': r['verdict']='DIAGNOSTIC_TIMEOUT'
if mode=='delay': time.sleep(.6)
(d/'receipt.json').write_text(json.dumps(r),encoding='utf-8')
'''


class GateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sentinel = self.root/'forbidden-start'

    def tearDown(self):
        self.temp.cleanup()

    def batch(self, accepted=('PASS',), second_kind='device'):
        specs = [{'id':'first','kind':'diagnostic','accept':list(accepted)},
                 {'id':'second','kind':second_kind,'accept':['PASS']}]
        return Batch.create(self.root/'batch','test-r3','a'*64,specs)

    def call(self, batch, mode, timeout=3):
        return batch.run('first',[sys.executable,'-c',FAKE,mode],timeout=timeout)

    def blocked(self, batch):
        for obj in (batch, Batch(self.root/'batch')):
            with self.assertRaises(GateClosed):
                obj.run('second',[sys.executable,'-c',
                    'from pathlib import Path; Path('+repr(str(self.sentinel))+').touch()'],timeout=2)
        self.assertFalse(self.sentinel.exists())
        state=json.loads((self.root/'batch/state.json').read_text(encoding='utf-8'))
        self.assertEqual(state['status'],'HALTED')
        dispatched=json.loads((self.root/'batch/commands/first/dispatch.json').read_text(encoding='utf-8'))['pid']
        self.assertEqual(state['unrun'],['second'] if dispatched else ['first','second'])

    def test_nonzero_and_malformed_receipts_block_actual_subprocess(self):
        for mode in ('nonzero','missing','badjson','old','hash','unsafe','safety_stop',
                     'noaudit','corrupt','path','types','safety_missing','duplicates'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                old=self.root; self.root=Path(folder)
                try:
                    b=self.batch(second_kind='model')
                    with self.assertRaises(GateClosed): self.call(b,mode)
                    self.blocked(b)
                finally: self.root=old

    def test_timeout_blocks(self):
        b=self.batch()
        with self.assertRaises(GateClosed): self.call(b,'hang',.12)
        self.blocked(b)

    def test_positive_only_allows_registered_next_command(self):
        b=self.batch(); self.call(b,'pass')
        with self.assertRaises(GateClosed): b.run('unknown',[sys.executable,'-c','pass'],timeout=1)
        self.assertFalse(self.sentinel.exists())

    def test_expected_refusal_is_not_business_success(self):
        b=self.batch(('EXPECTED_REFUSAL',)); r=self.call(b,'refusal')
        self.assertEqual(r['verdict'],'EXPECTED_REFUSAL')
        self.assertFalse(b.state()['business_success'])

    def test_registered_timeout_does_not_release_device_or_model(self):
        b=self.batch(('PASS','DIAGNOSTIC_TIMEOUT')); self.call(b,'timeout')
        with self.assertRaises(GateClosed):
            b.run('second',[sys.executable,'-c','pass'],timeout=1)
        self.assertFalse(self.sentinel.exists())

    def test_unregistered_timeout_blocks(self):
        b=self.batch()
        with self.assertRaises(GateClosed): self.call(b,'timeout')
        self.blocked(b)

    def test_duplicate_command_cannot_reuse_old_pass(self):
        b=self.batch(); self.call(b,'pass')
        with self.assertRaises(GateClosed): self.call(b,'pass')
        self.blocked(b)

    def test_restart_while_running_fails_closed(self):
        b=self.batch(); state=b.state(); state['status']='RUNNING'
        (b.root/'state.json').write_text(json.dumps(state))
        with self.assertRaises(GateClosed): self.call(Batch(b.root),'pass')
        state=Batch(b.root).state(); self.assertEqual(state['status'],'HALTED')

    def test_cancel_before_admission(self):
        b=self.batch(); b.cancel()
        with self.assertRaises(GateClosed): self.call(b,'pass')
        self.assertFalse((b.root/'commands/first').exists())

    def test_cancel_during_wait_and_late_pass_cannot_revive(self):
        b=self.batch(); timer=threading.Timer(.15,b.cancel); timer.start()
        try:
            with self.assertRaises(GateClosed): self.call(b,'delay')
        finally: timer.join()
        self.blocked(b)
        (b.root/'commands/first/receipt.json').write_text('{"verdict":"PASS"}')
        self.blocked(Batch(b.root))

    def test_process_start_error_blocks(self):
        b=self.batch()
        with self.assertRaises(GateClosed): b.run('first',['not-a-real-r3-executable'],timeout=1)
        self.blocked(b)

    def test_held_lock_prevents_concurrent_dispatch(self):
        b=self.batch(); errors=[]
        def first():
            try: self.call(b,'delay')
            except Exception as e: errors.append(e)
        thread=threading.Thread(target=first); thread.start()
        until=time.monotonic()+2
        while not (b.root/'commands/first').exists() and time.monotonic()<until: time.sleep(.01)
        with self.assertRaises(GateClosed):
            Batch(b.root).run('second',[sys.executable,'-c','pass'],timeout=1)
        thread.join(); self.assertEqual(errors,[])

    def test_timeout_kills_only_owned_tree(self):
        unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'])
        try:
            b=self.batch()
            with self.assertRaises(GateClosed): self.call(b,'hang',.12)
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate(); unrelated.wait()

    def test_complete_positive_sequence(self):
        b=self.batch(); self.call(b,'pass')
        b.run('second',[sys.executable,'-c',FAKE,'pass'],timeout=3)
        self.assertEqual(b.state()['unrun'],[])

    def test_manifest_tampering_blocks(self):
        b=self.batch(); path=b.root/'manifest.json'
        path.write_text(path.read_text()+' ')
        with self.assertRaises(GateClosed): self.call(b,'pass')
        self.assertFalse((b.root/'commands/first').exists())

    def test_receipt_validation_cancel_blocks_next(self):
        b=self.batch(); original=b._validate
        def cancelled(*args):
            b.cancel(); return original(*args)
        b._validate=cancelled
        with self.assertRaises(GateClosed): self.call(b,'pass')
        with self.assertRaises(GateClosed):
            b.run('second',[sys.executable,'-c','pass'],timeout=1)

    def test_predeclared_timeout_can_only_continue_diagnostic(self):
        b=Batch.create(self.root/'batch','test-r3','a'*64,[
            {'id':'first','kind':'diagnostic','accept':['PASS','DIAGNOSTIC_TIMEOUT']},
            {'id':'second','kind':'diagnostic','accept':['PASS','DIAGNOSTIC_TIMEOUT']}])
        self.call(b,'timeout')
        b.run('second',[sys.executable,'-c',FAKE,'timeout'],timeout=3)
        self.assertTrue(b.state()['performance_failed'])
        self.assertFalse(b.state()['business_success'])

    def test_registered_source_change_blocks_before_dispatch(self):
        from repair_r3_gate import sha
        source=self.root/'source.py'; source.write_bytes(b'original')
        b=Batch.create(self.root/'batch','test-r3','a'*64,[{'id':'first','kind':'device','accept':['PASS'],
            'source_files':{str(source):sha(source.read_bytes())}}])
        source.write_bytes(b'changed')
        with self.assertRaises(GateClosed): self.call(b,'pass')
        self.assertFalse((b.root/'commands/first').exists())

    @unittest.skipUnless(os.name=='nt','Windows owned-tree test')
    def test_cancel_terminates_owned_child_not_unrelated_process(self):
        import ctypes
        b=self.batch(); errors=[]
        unrelated=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'])
        def command():
            try: self.call(b,'child',5)
            except GateClosed: errors.append('closed')
        thread=threading.Thread(target=command); thread.start()
        try:
            pidfile=b.root/'commands/first/child.pid'; until=time.monotonic()+3
            while not pidfile.exists() and time.monotonic()<until: time.sleep(.02)
            self.assertTrue(pidfile.exists()); child=int(pidfile.read_text())
            b.cancel(); thread.join(6); self.assertFalse(thread.is_alive())
            self.assertEqual(errors,['closed']); self.assertIsNone(unrelated.poll())
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.restype=ctypes.c_void_p
            kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.OpenProcess(0x1000,False,child)
            if handle:
                try:
                    code=ctypes.c_ulong(); self.assertTrue(kernel.GetExitCodeProcess(handle,ctypes.byref(code)))
                    self.assertNotEqual(code.value,259)
                finally: kernel.CloseHandle(handle)
        finally:
            b.cancel(); thread.join(6); unrelated.terminate(); unrelated.wait()


if __name__=='__main__': unittest.main()
