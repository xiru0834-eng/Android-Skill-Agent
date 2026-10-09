"""H3 test-operator guard for this emulator's InputDispatcher dump format.

Never used inside the skill executor. Unknown formats fail closed.
"""
import re
import time


def ready_window(dump,activity,x,y):
    # Android appends a past ANR snapshot with the same field names. It is not live state.
    dump=dump.split('Input Dispatcher State at time of last ANR:',1)[0]
    focus=re.search(r'FocusedWindows:\s*\n(.*?)(?=\n\s*FocusRequests:)',dump,re.S)
    if not focus:return None
    names=re.findall(r"displayId=0, name='([^']+)'",focus.group(1))
    if len(names)!=1 or not names[0].endswith(' '+activity):return None
    lines=[line.strip() for line in dump.splitlines() if re.match(r'\s*\d+: name=',line) and "name='"+names[0]+"'" in line]
    if len(lines)!=1:return None
    line=lines[0]
    config=re.search(r'inputConfig=([^,]+)',line)
    if not config or config.group(1)!='0x0':return None
    if ', displayId=0,' not in line or 'alpha=1.00,' not in line or 'globalScale=1.000000,' not in line:return None
    region=re.search(r'touchableRegion=(.*?), ownerPid=',line)
    if not region:return None
    rectangles=re.findall(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',region.group(1))
    if not any(int(l)<=x<int(r) and int(t)<=y<int(b) for l,t,r,b in rectangles):return None
    return line


def wait_input_ready(read,activity,x,y,clock=time.monotonic,sleep=time.sleep):
    started=clock();checks=0;previous=None
    while clock()-started<8:
        dump=read();checks+=1;current=ready_window(dump,activity,x,y)
        if current is not None and current==previous:
            return dict(checks=checks,waitMs=round((clock()-started)*1000),window=current)
        previous=current;sleep(.15)
    raise RuntimeError('Input window not ready; no tap issued')
