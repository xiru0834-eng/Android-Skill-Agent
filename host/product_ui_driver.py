"""Evaluator controls actual existing UI in a persistent real process, not a shadow page."""
import json,time,uuid
from lab_transport import adb

def ui(host,operation,control=None,text=None,confirmed=False):
    rid=uuid.uuid4().hex
    if text is not None:
        data=json.dumps({'request_id':rid,'text':text},ensure_ascii=False).encode()
        adb(host,'shell','run-as','edu.sydney.probe','sh','-c',"'cat > files/product-ui-incoming.json'",input=data)
    args=['shell','am','broadcast','--receiver-foreground','-a','edu.sydney.probe.PRODUCT_UI_AUDIT','-n','edu.sydney.probe/.ProductUiAuditReceiver',
        '--es','request_id',rid,'--es','operation',operation,'--ez','confirmed',str(confirmed).lower()]
    if control:args+=['--es','control',control]
    adb(host,*args)
    for _ in range(20):
        try:return json.loads(adb(host,'shell','run-as','edu.sydney.probe','cat','files/product-ui-audit-'+rid+'.json'))
        except RuntimeError:time.sleep(.05)
    raise ValueError('UI_AUDIT_NOT_RETURNED')

def control(host,op,name=None,text=None,confirmed=False):
    # Evaluator UI visibility only, before native task admission. A slow scroll
    # acknowledgement may consume the former 4s before the next fresh read.
    # Native whole-Flow 8s and model selection 20s are untouched.
    until=time.monotonic()+12
    scrolls=0
    while time.monotonic()<until:
        receipt=ui(host,op,name,text,confirmed)
        if receipt.get('status')!='REJECTED':return receipt
        reason=receipt.get('reason')
        if reason=='OWN_UI_NOT_ACTIVE':
            # Activity transitions are asynchronous. Only re-observe; never click
            # another package or dismiss an unknown dialog to make a test pass.
            time.sleep(.1);continue
        if reason=='UI_CONTROL_NOT_UNIQUE':
            snapshot=ui(host,'dump')
            resource='android:id/button1' if op=='confirm_dialog' else 'edu.sydney.probe:id/'+str(name)
            matches=[n for n in snapshot.get('nodes',[]) if n.get('resource_id')==resource]
            if len(matches)<=1:time.sleep(.1);continue
            raise ValueError('NORMAL_UI_AMBIGUOUS_CONTROL')
        if reason!='UI_CONTROL_NOT_VISIBLE':raise ValueError('NORMAL_UI_'+str(reason))
        if scrolls>=8:break
        ui(host,'scroll');scrolls+=1;time.sleep(.12)
    raise ValueError('NORMAL_UI_CONTROL_NOT_VISIBLE')

def read(host,name):
    try:return adb(host,'shell','run-as','edu.sydney.probe','cat','files/'+name).decode()
    except RuntimeError:return ''

def drive(host,text,review=False,cancel=False):
    audit=[]
    timing={'clock':'HOST_MONOTONIC_NS','driver_started':time.monotonic_ns()}
    # Explicit normal launcher; buttons are then actual current Accessibility nodes.
    # A launcher can resume its previous child Activity. This test explicitly
    # returns to the normal Home screen, without restarting the service process.
    adb(host,'shell','am','start','-f','0x14000000','-n','edu.sydney.probe/.MainActivity');time.sleep(.25)
    audit.append(control(host,'click','portableEntry'))
    if review:
        audit.append(control(host,'click','publishedFlowReview'));time.sleep(.15)
        audit.append(control(host,'confirm_dialog',confirmed=True));time.sleep(.15)
    old_selection=read(host,'flow-user-selection.json');old_result=read(host,'flow-user-result.json')
    audit.append(control(host,'fill','portableInput',text));timing['input_filled']=time.monotonic_ns()
    audit.append(control(host,'click','publishedFlowUnderstand'));timing['understand_click_ack']=time.monotonic_ns()
    if cancel:
        time.sleep(.1);audit.append(control(host,'click','portableStop'));time.sleep(1)
        visible=ui(host,'dump')
        status=next((n.get('text','') for n in visible.get('nodes',[]) if n.get('resource_id')=='edu.sydney.probe:id/portableStatus'),'')
        # Wait beyond the unchanged selection deadline. The late network callback
        # must not replace the cancelled UI state or create a selection/result.
        time.sleep(20)
        late=ui(host,'dump')
        late_status=next((n.get('text','') for n in late.get('nodes',[]) if n.get('resource_id')=='edu.sydney.probe:id/portableStatus'),'')
        confirmed='CANCELLED' in status and 'CANCELLED' in late_status and read(host,'flow-user-selection.json')==old_selection and read(host,'flow-user-result.json')==old_result
        return {'cancel_status':'USER_CANCELLED' if confirmed else 'UNCONFIRMED','error':None if confirmed else 'CANCEL_NOT_PROVEN',
            'cancel_visible':visible,'late_visible':late,'late_callback_wait_ms':20000,
            'ui_audit':audit,'channel':'EVALUATOR_UI_ACTION_NORMAL_PRODUCT_ENTRY','timings_ns':{**timing,'driver_finished':time.monotonic_ns()}}
    until=time.monotonic()+23;selection=None
    while time.monotonic()<until:
        raw=read(host,'flow-user-selection.json')
        if raw!=old_selection and raw:
            selection=json.loads(raw);break
        time.sleep(.1)
    if selection is None:return {'error':'NORMAL_UI_SELECTION_NOT_RETURNED','ui_audit':audit,'visible_error':ui(host,'dump'),'timings_ns':{**timing,'driver_finished':time.monotonic_ns()}}
    timing['selection_observed']=time.monotonic_ns()
    out={'selection':selection,'ui_audit':audit,'channel':'EVALUATOR_UI_ACTION_NORMAL_PRODUCT_ENTRY','timings_ns':timing}
    if selection['status']=='invoke':
        time.sleep(.1);audit.append(control(host,'confirm_dialog',confirmed=True));timing['confirm_click_ack']=time.monotonic_ns();until=time.monotonic()+13
        while time.monotonic()<until:
            raw=read(host,'flow-user-result.json')
            if raw!=old_result and raw:
                out['result']=json.loads(raw);timing['receipt_observed']=time.monotonic_ns();break
            time.sleep(.1)
        if 'result' not in out:out['error']='NORMAL_UI_RESULT_NOT_RETURNED'
        adb(host,'shell','input','keyevent','KEYCODE_BACK');time.sleep(.15)
        out['visible_result']=ui(host,'dump')
    timing['driver_finished']=time.monotonic_ns();return out
