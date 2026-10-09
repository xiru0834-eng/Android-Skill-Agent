"""Compile a new automated trace, reject a duplicate name via normal Save UI."""
import json
import time
from pathlib import Path
from named_journey_device import prefs,tap,text,snap
from workflow_experiment import write

def main():
    s='R5CW134LLBZ';out=Path('evaluation/named-journey/name-conflict-ui');out.mkdir(exist_ok=False)
    before=prefs(s);write(out/'before.json',before);tap(s,'teachGenerate')
    for _ in range(55):
        state=prefs(s,'teaching_journey')
        if state.get('draft'):break
        time.sleep(1)
    else:raise RuntimeError('No new draft')
    write(out/'draft.json',json.loads(state['draft']));tap(s,'teachSave');snap(s,out/'duplicate-name.png');tap(s,'button1','android')
    after=prefs(s);assert after.get('library')==before.get('library') and after.get('approved')==before.get('approved')
    assert after.get('result')==before.get('result');write(out/'after.json',after);snap(s,out/'rejected.png')
    tap(s,'teachSave');text(s,'teachSaveName','Editable name - cancelled');snap(s,out/'editable-name.png');tap(s,'button2','android')
    assert prefs(s)['library']==before['library']
    write(out/'score.json',dict(duplicateRejected=True,oldCatalogPreserved=True,editableName=True,cancelDidNotSave=True))
    print('Duplicate-name and editable-name UI checks passed',flush=True)

if __name__=='__main__':main()
