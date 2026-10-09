"""Finite, current-authorized continuation ledger; r1 stays sealed."""
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
import g3_device_eval as g3
from lab_transport import adb
from prepare_g1 import save
from repair_r2 import prepare_current

ROOT = Path(__file__).parent
RUN = ROOT / 'evidence/flow-deadline-repair/r2'
PRIVATE = ROOT / 'private/flow-deadline-repair-r2'
PHASES = ['baseline-emulator', 'final-phone', 'final-emulator',
          'repeat-phone-1', 'repeat-phone-2', 'repeat-emulator-1', 'repeat-emulator-2']

def run(host, out, phase):
    if out.exists():
        raise ValueError('PRESERVE_OLD_BATCH')
    main_calls = 7 if phase.startswith('final-') else 1
    current_ledgers = [json.loads(p.read_text(encoding='utf-8')) for p in RUN.rglob('paid-budget.json')]
    attempts = sum(x['attempts'] for x in current_ledgers)
    exposure = sum(x['exposureNanoUsd'] for x in current_ledgers)
    max_exposure = (main_calls + 1) * 50_000_000
    if attempts + main_calls + 1 > 32 or exposure + max_exposure > 1_000_000_000:
        raise ValueError('CURRENT_BATCH_LIMIT')
    save(RUN/'allocations'/(out.name+'.json'),
         {'human_authorized': True, 'max_attempts': 32, 'estimated_usd_cap': 1,
          'phase': phase, 'main_calls': main_calls, 'fresh_calls': 1,
          'session_reservation_nano_usd': max_exposure, 'automatic_retries': 0,
          'input_byte_cap': 65536, 'output_token_cap': 512, 'actual_invoice': 'UNKNOWN'})
    reconnect = g3.reconnect
    g3.reconnect = lambda h: reconnect(h, PRIVATE/h/'snapshot.json')
    g3.prepare = prepare_current

    def bridge(h, knowledge, path, port, ignored):
        fresh = path.name == 'fresh-session'
        count = 1 if fresh else main_calls
        log = (path/'bridge.log').open('w', encoding='utf-8')
        proc = subprocess.Popen([sys.executable, '-u', str(ROOT/'flow_bridge.py'), str(knowledge),
                                 str(path/'model-audit'), '--host', h, '--port', str(port),
                                 '--max-calls', str(count), '--max-nano-usd', str(count*50_000_000)],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            for _ in range(80):
                if proc.poll() is not None:
                    raise ValueError('BRIDGE_START_FAILED')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.05)
            else:
                raise ValueError('BRIDGE_NOT_READY')
            adb(h, 'reverse', 'tcp:8765', 'tcp:'+str(port))
            save(path/'gateway-session.json', {'pid': proc.pid, 'fresh_process': fresh,
                 'max_calls': count, 'max_nano_usd': count*50_000_000, 'automatic_retry': False})
            return proc, log
        except Exception:
            proc.terminate(); proc.wait(5); log.close()
            raise
    g3.bridge = bridge
    knowledge = ROOT/('evidence/g2-native-reviewed-knowledge-r2.json' if host=='R5CW134LLBZ'
                     else 'evidence/g4-real-package-transfer-r1/target-native-knowledge.json')
    g3.run(host, knowledge, out, 49721 if host=='R5CW134LLBZ' else 49722,
           case_names=None if phase.startswith('final-') else ['explicit', 'new_session'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--phase', required=True, choices=PHASES)
    args = parser.parse_args()
    run(args.host, args.out, args.phase)
