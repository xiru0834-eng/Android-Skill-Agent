"""Separate continuation batch. Never overwrite the sealed r1 evidence/snapshot."""
import argparse
import json
import time
from pathlib import Path
import deadline_repair_eval as evaluation

ROOT = Path(__file__).parent
evaluation.RUN = ROOT / 'evidence/flow-deadline-repair/r2'
evaluation.PRIVATE = ROOT / 'private/flow-deadline-repair-r2'

def prepare_current(host, case, initial=(0, 50, 0, 22), fault='normal', delay=0):
    """Evaluator setup only; task admission/deadline has not started."""
    from lab_transport import adb
    from g1_device_eval import oracle
    adb(host, 'shell', 'am', 'start', '-n', 'edu.sydney.parameterroom/.ParameterRoomActivity',
        '--es', 'initial', ','.join(map(str, initial)), '--es', 'caseId', case,
        '--es', 'fault', fault, '--ei', 'commitDelayMs', str(delay))
    started = time.monotonic()
    latest = None
    while time.monotonic() - started < 12:
        try:
            latest = oracle(host)
            if latest['case_id'] == case and latest['initial'] == list(initial) and not latest['events']:
                return latest
        except (json.JSONDecodeError, RuntimeError):
            pass
        time.sleep(.1)
    evaluation.save(evaluation.RUN / 'initialization-failures' / (case + '.json'),
                    {'host': host, 'latest_oracle': latest, 'elapsed_ms': (time.monotonic()-started)*1000,
                     'task_started': False, 'native_deadline_unchanged': True})
    raise RuntimeError('INITIALIZATION_FAILED')

evaluation.prepare = prepare_current

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['snapshot', 'install', 'diagnostic'])
    parser.add_argument('--out', type=Path)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--hosts', nargs='+', default=['emulator-5556', 'R5CW134LLBZ'])
    args = parser.parse_args()
    if args.operation == 'snapshot':
        evaluation.snapshot()
    elif args.operation == 'install':
        for host in args.hosts:
            evaluation.install(host, args.apk)
    else:
        evaluation.diagnostic(args.out, args.hosts)
