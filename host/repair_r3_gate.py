"""Host-only sequential, persistent fail-closed command gate; no product imports."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


class GateClosed(RuntimeError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path, data):
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


class Batch:
    @classmethod
    def create(cls, root, batch_id, candidate_hash, commands):
        root = Path(root)
        if not re.fullmatch('[a-zA-Z0-9_.-]{1,100}', batch_id) or not re.fullmatch('[a-f0-9]{64}', candidate_hash):
            raise ValueError('BATCH_IDENTITY')
        ids = []
        for command in commands:
            if (not re.fullmatch('[a-zA-Z0-9_.-]{1,100}', command['id'])
                    or command['id'] in ids or command['kind'] not in {'diagnostic','device','model','local','analysis'}
                    or not command['accept'] or not set(command['accept']) <= {'PASS','EXPECTED_REFUSAL','DIAGNOSTIC_TIMEOUT'}):
                raise ValueError('COMMAND_SPEC')
            if 'DIAGNOSTIC_TIMEOUT' in command['accept'] and command['kind'] != 'diagnostic':
                raise ValueError('DIAGNOSTIC_SCOPE')
            ids.append(command['id'])
        root.mkdir(parents=True, exist_ok=False)
        manifest = {'batch_id':batch_id,'candidate_hash':candidate_hash,'commands':commands}
        atomic(root/'manifest.json', manifest)
        atomic(root/'state.json', {'status':'ACTIVE','next':0,'unrun':ids,
               'manifest_hash':sha((root/'manifest.json').read_bytes()),'performance_failed':False,
               'business_success':False,'reason':None})
        return cls(root)

    def __init__(self, root):
        self.root = Path(root)

    def state(self):
        return strict_json((self.root/'state.json').read_text(encoding='utf-8'))

    def cancel(self):
        # Independent of the dispatch lock: cancellation must interrupt a waiter.
        with (self.root/'cancel.request').open('ab') as handle:
            handle.write(b'CANCEL\n'); handle.flush(); os.fsync(handle.fileno())

    def _halt(self, state, reason):
        state.update(status='HALTED',reason=state.get('reason') or reason)
        atomic(self.root/'state.json', state)
        raise GateClosed(reason)

    def _validate(self, folder, manifest, command, state):
        raw=(folder/'receipt.json').read_bytes()
        if len(raw)>1048576:
            raise ValueError('RECEIPT_SIZE')
        receipt=strict_json(raw.decode('utf-8'))
        for key, expected in [('batch_id',manifest['batch_id']),('candidate_hash',manifest['candidate_hash']),('command_id',command['id'])]:
            if receipt.get(key)!=expected:
                raise ValueError('RECEIPT_IDENTITY_'+key)
        safety=receipt['safety']
        for key in ('wrong_action','false_success','prohibited_side_effect','post_cancel_dispatch'):
            if type(safety.get(key)) is not bool or safety[key]:
                raise ValueError('SAFETY_STOP_'+key)
        audit=receipt['audit']; relative=Path(audit['path'])
        path=(folder/relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(folder.resolve()) or sha(path.read_bytes())!=audit['sha256']:
            raise ValueError('AUDIT_MISSING_OR_INVALID')
        if receipt['verdict'] not in command['accept']:
            raise ValueError('UNEXPECTED_VERDICT_'+str(receipt['verdict']))
        state['performance_failed'] |= receipt['verdict']=='DIAGNOSTIC_TIMEOUT'
        state['business_success']=receipt['verdict']=='PASS' and command['kind'] in {'device','model'}
        return receipt

    @staticmethod
    def _stop_owned(process):
        if process is None or process.poll() is not None:
            return
        # Exact live Popen root, never a global image/name match. Windows /T
        # includes only its descendants; unrelated Python/ADB remains untouched.
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5)
        else:
            import signal
            os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=5)

    def run(self, command_id, argv, *, timeout, cwd=None):
        lock=(self.root/'dispatch.lock').open('a+b')
        try:
            if os.name=='nt':
                import msvcrt
                lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise GateClosed('CONCURRENT_DISPATCH_BLOCKED')
        process=None; record=None; state=None
        try:
            state=self.state()
            manifest_raw=(self.root/'manifest.json').read_bytes()
            if sha(manifest_raw)!=state['manifest_hash']:
                self._halt(state,'MANIFEST_CHANGED')
            manifest=strict_json(manifest_raw.decode('utf-8'))
            if state['status']!='ACTIVE':
                self._halt(state,'PERSISTENT_STOP_OR_INTERRUPTED_RUN')
            if (self.root/'cancel.request').exists():
                self._halt(state,'CANCELLED_BEFORE_ADMISSION')
            specs=manifest['commands']; index=state['next']
            if index>=len(specs) or specs[index]['id']!=command_id:
                self._halt(state,'NOT_REGISTERED_NEXT_COMMAND')
            command=specs[index]
            if 'argv_sha256' in command and command['argv_sha256']!=sha(json.dumps(argv).encode()):
                self._halt(state,'COMMAND_ARGV_CHANGED')
            for name, expected in command.get('source_files',{}).items():
                if sha(Path(name).read_bytes())!=expected:
                    self._halt(state,'COMMAND_SOURCE_CHANGED')
            if state['performance_failed'] and command['kind'] not in {'diagnostic','analysis','local'}:
                self._halt(state,'PERFORMANCE_GATE_CLOSED')
            folder=self.root/'commands'/command_id; folder.mkdir(parents=True,exist_ok=False)
            state.update(status='RUNNING',active_command=command_id)
            atomic(self.root/'state.json',state)  # durable before Popen
            record={'command_id':command_id,'batch_id':manifest['batch_id'],
                    'candidate_hash':manifest['candidate_hash'],'argv':argv,
                    'started_monotonic_ns':time.monotonic_ns(),'exit_code':None,'pid':None}
            atomic(folder/'dispatch.json',record)
            env=dict(os.environ,R3_COMMAND_DIR=str(folder.resolve()),R3_BATCH_ID=manifest['batch_id'],
                     R3_COMMAND_ID=command_id,R3_CANDIDATE_HASH=manifest['candidate_hash'])
            if (self.root/'cancel.request').exists():
                self._halt(state,'CANCELLED_BEFORE_DISPATCH')
            with (folder/'stdout.log').open('wb') as stdout, (folder/'stderr.log').open('wb') as stderr:
                process=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stdout,stderr=stderr,shell=False,
                    start_new_session=os.name!='nt',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                record['pid']=process.pid; atomic(folder/'dispatch.json',record)
                state['unrun']=[s['id'] for s in specs[index+1:]]
                atomic(self.root/'state.json',state)
                until=time.monotonic()+timeout
                while process.poll() is None:
                    if (self.root/'cancel.request').exists():
                        self._halt(state,'CANCELLED_WHILE_RUNNING')
                    if time.monotonic()>=until:
                        self._halt(state,'COMMAND_TIMEOUT')
                    time.sleep(.02)
            record['exit_code']=process.returncode
            if process.returncode!=0:
                self._halt(state,'NONZERO_EXIT')
            if (self.root/'cancel.request').exists():
                self._halt(state,'CANCELLED_BEFORE_DELIVERY')
            receipt=self._validate(folder,manifest,command,state)
            if (self.root/'cancel.request').exists():
                self._halt(state,'CANCELLED_DURING_DELIVERY')
            record.update(decision='ACCEPTED',receipt_sha256=sha((folder/'receipt.json').read_bytes()))
            state.update(status='ACTIVE',next=index+1,unrun=[s['id'] for s in specs[index+1:]],active_command=None)
            atomic(self.root/'state.json',state)
            return receipt
        except BaseException as error:
            if state is not None:
                state.update(status='HALTED',reason=state.get('reason') or type(error).__name__+':'+str(error))
                atomic(self.root/'state.json',state)
            self._stop_owned(process)
            if record is not None:
                record.update(decision='BLOCKED',reason=str(error),exit_code=process.returncode if process else None)
            if isinstance(error,(KeyboardInterrupt,SystemExit)):
                raise
            raise GateClosed(str(error)) from error
        finally:
            if record is not None:
                record['finished_monotonic_ns']=time.monotonic_ns()
                atomic(self.root/'commands'/command_id/'dispatch.json',record)
            lock.close()
