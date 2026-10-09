"""Result collection window begins after the one normal UI click returns."""
import json
import subprocess
import time


def wait_terminal(read,previous_run,clock=time.monotonic,sleep=time.sleep,budget_seconds=35):
    deadline=clock()+budget_seconds
    while clock()<deadline:
        try:result=read()
        except (RuntimeError,json.JSONDecodeError,subprocess.TimeoutExpired):sleep(.15);continue
        if (isinstance(result,dict) and result.get('runId') and result['runId']!=previous_run
                and result.get('status') in ('SUCCEEDED','UNCONFIRMED','CANCELLED')):
            return result
        sleep(.1)
    raise RuntimeError('No new terminal result in post-click collection window')
