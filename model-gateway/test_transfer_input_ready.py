import unittest
from transfer_input_ready import ready_window,wait_input_ready


ACTIVITY='edu.sydney.probe/edu.sydney.probe.WorkflowActivity'
FOCUS="  FocusedWindows:\n    displayId=0, name='abc "+ACTIVITY+"'\n  FocusRequests:\n"
WINDOW="  0: name='abc "+ACTIVITY+"', id=7, displayId=0, inputConfig=0x0, alpha=1.00, frame=[0,0][1080,2400], globalScale=1.000000, touchableRegion=[0,0][1080,2400], ownerPid=2\n"


class ReadyTests(unittest.TestCase):
    def test_historical_anr_window_does_not_look_like_duplicate_live_window(self):
        dump='Input Dispatcher State:\n'+FOCUS+WINDOW+'Input Dispatcher State at time of last ANR:\n'+FOCUS+WINDOW
        self.assertIsNotNone(ready_window(dump,ACTIVITY,540,1566))
    def test_historical_anr_alone_is_not_ready(self):
        self.assertIsNone(ready_window('Input Dispatcher State at time of last ANR:\n'+FOCUS+WINDOW,ACTIVITY,540,1566))
    def test_requires_two_ready_checks(self):
        state=[0,0]
        def read():state[1]+=1;return FOCUS+WINDOW
        def sleep(s):state[0]+=s
        result=wait_input_ready(read,ACTIVITY,540,1566,lambda:state[0],sleep)
        self.assertEqual(result['checks'],2);self.assertEqual(state[1],2)
    def test_timeout_without_ready_window(self):
        state=[0]
        def sleep(s):state[0]+=s
        self.assertRaises(RuntimeError,wait_input_ready,lambda:'',ACTIVITY,540,1566,lambda:state[0],sleep)
    def test_ready(self):self.assertIsNotNone(ready_window(FOCUS+WINDOW,ACTIVITY,540,1566))
    def test_no_focus(self):self.assertIsNone(ready_window(WINDOW,ACTIVITY,540,1566))
    def test_different_activity(self):self.assertIsNone(ready_window(FOCUS+WINDOW,ACTIVITY+'Other',540,1566))
    def test_untouchable(self):self.assertIsNone(ready_window(FOCUS+WINDOW.replace('0x0','NOT_TOUCHABLE'),ACTIVITY,540,1566))
    def test_hidden(self):self.assertIsNone(ready_window(FOCUS+WINDOW.replace('0x0','NOT_VISIBLE'),ACTIVITY,540,1566))
    def test_no_channel(self):self.assertIsNone(ready_window(FOCUS+WINDOW.replace('0x0','NO_INPUT_CHANNEL'),ACTIVITY,540,1566))
    def test_empty_region(self):self.assertIsNone(ready_window(FOCUS+WINDOW.replace('touchableRegion=[0,0][1080,2400]','touchableRegion=<empty>'),ACTIVITY,540,1566))
    def test_outside_region(self):self.assertIsNone(ready_window(FOCUS+WINDOW,ACTIVITY,1200,1566))
    def test_invisible_alpha(self):self.assertIsNone(ready_window(FOCUS+WINDOW.replace('alpha=1.00','alpha=0.00'),ACTIVITY,540,1566))
    def test_no_window(self):self.assertIsNone(ready_window(FOCUS,ACTIVITY,540,1566))


if __name__=='__main__':unittest.main()
