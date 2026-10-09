import unittest
import subprocess
from transfer_terminal_wait import wait_terminal


class Clock:
    def __init__(self):self.now=20.0
    def time(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class WaitTests(unittest.TestCase):
    def test_slow_button_preparation_does_not_steal_execution_collection_time(self):
        clock=Clock()
        def read():return dict(runId='new',status='SUCCEEDED' if clock.now>=50 else 'RUNNING')
        self.assertEqual(wait_terminal(read,'old',clock.time,clock.sleep)['status'],'SUCCEEDED')
        self.assertLess(clock.now,55.1)
    def test_stale_terminal_is_not_accepted(self):
        clock=Clock()
        self.assertRaises(RuntimeError,wait_terminal,lambda:dict(runId='old',status='SUCCEEDED'),'old',clock.time,clock.sleep)
        self.assertGreaterEqual(clock.now,55)
        self.assertLess(clock.now,55.2)
    def test_running_is_not_terminal(self):
        clock=Clock()
        self.assertRaises(RuntimeError,wait_terminal,lambda:dict(runId='new',status='RUNNING'),'old',clock.time,clock.sleep)
    def test_execution_timeout_collected_but_never_changed_to_success(self):
        clock=Clock()
        value=wait_terminal(lambda:dict(runId='new',status='UNCONFIRMED',reason='TASK_TIMEOUT'),'old',clock.time,clock.sleep)
        self.assertEqual(value['reason'],'TASK_TIMEOUT');self.assertEqual(value['status'],'UNCONFIRMED')
    def test_malformed_status_not_accepted(self):
        clock=Clock()
        self.assertRaises(RuntimeError,wait_terminal,lambda:dict(runId='new'),'old',clock.time,clock.sleep)
    def test_one_read_timeout_can_recover_without_clicking_again(self):
        clock=Clock();calls=[]
        def read():
            calls.append(1)
            if len(calls)==1:raise subprocess.TimeoutExpired('read-only adb',2)
            return dict(runId='new',status='UNCONFIRMED')
        self.assertEqual(wait_terminal(read,'old',clock.time,clock.sleep)['status'],'UNCONFIRMED')
        self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
