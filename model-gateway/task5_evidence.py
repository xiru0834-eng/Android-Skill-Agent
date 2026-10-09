"""Read-only evidence receipts and raw adjudication, without device or network calls."""
import hashlib
import json
from pathlib import Path
from task5_protocol import decode, safe_name, latency, MAX_BYTES
from task3_audit import rejudge
from skill_selection import validate_selection


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class ReceiptReader:
    def __init__(self,root):
        self.root=Path(root).resolve();self.receipts={};self.blobs={}

    def path(self,name):
        safe_name(name);path=self.root/name
        if any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(self.root)):raise ValueError('LINK_NOT_ALLOWED')
        if not path.resolve().is_relative_to(self.root):raise ValueError('OUTSIDE_EVIDENCE_ROOT')
        return path

    def has(self,name):return self.path(name).is_file()

    def raw(self,name):
        path=self.path(name)
        if path.stat().st_size>MAX_BYTES:raise ValueError('FILE_SIZE')
        blob=path.read_bytes()
        # All collected evidence is UTF-8 text; validate JSON before copying it.
        if name.endswith('.json'):decode(blob)
        else:
            text=blob.decode('utf-8','strict')
            if any(s in text.lower() for s in ['sk-proj-','apikey_','<string name="pairing"']):raise ValueError('SENSITIVE_VALUE')
        receipt=dict(byteCount=len(blob),sha256=hashlib.sha256(blob).hexdigest())
        if name in self.receipts and self.receipts[name]!=receipt:raise ValueError('INPUT_CHANGED_DURING_READ')
        self.receipts[name]=receipt;self.blobs[name]=blob
        return blob

    def read(self,name):return decode(self.raw(name))

    def snapshot(self,out):
        out=Path(out);out.mkdir(parents=True,exist_ok=False)
        for name,blob in self.blobs.items():
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)


def replay_verify(root,receipts):
    reader=ReceiptReader(root);errors=[]
    for name,expected in receipts.items():
        try:
            reader.raw(name)
            if reader.receipts[name]!=expected:errors.append(dict(path=name,reason='BYTES_OR_HASH_DIFFERS'))
        except (OSError,ValueError):errors.append(dict(path=name,reason='MISSING_OR_INVALID'))
    return dict(valid=not errors,files=len(receipts),errors=errors)


def judge_run(data):
    checked=rejudge(*data)
    state='PASS' if checked['correctCompletion'] else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED')
    return dict(state=state,**checked)


def received_language(case,row,request,response,model,budget_seconds=8):
    errors=[];correct=False;within=False
    try:
        if canonical(row['case'])!=canonical(case):errors.append('CASE_DIFFERS')
        if request['model']!=model or response['returned_model']!=model:errors.append('MODEL_DIFFERS')
        content=decode(request['input'][-1]['content'].encode())
        if canonical(content)!=canonical(dict(text=case['text'],skills=case['skills'])):errors.append('REQUEST_DIFFERS')
        draft=validate_selection(response['draft'],case['skills'])
        if canonical(row['selection'])!=canonical(draft):errors.append('ROW_RESPONSE_DIFFERS')
        if response.get('raw_text') is not None and canonical(decode(response['raw_text'].encode()))!=canonical(draft):errors.append('RAW_RESPONSE_DIFFERS')
        if not isinstance(response['request_id'],str) or not response['request_id']:errors.append('REQUEST_ID_MISSING')
        if (type(row['remoteCalls']) is not int or row['remoteCalls']!=1 or len(row['calls'])!=1
                or row['calls'][0]['model']!=model or row['calls'][0]['provider']!='GPT'
                or row['calls'][0]['outcome']!='RETURNED'):errors.append('REMOTE_IDENTITY_OR_COUNT')
        latency([row['ms']],1)
        if type(budget_seconds) not in (int,float) or not 0<budget_seconds<=60:raise ValueError('INVALID_LANGUAGE_BUDGET')
        within=row['ms']<budget_seconds*1000
        correct=(draft['status'] in case['acceptableStatuses'] and draft['skill_id']==case['expected'])
    except (ValueError,KeyError,TypeError,IndexError):errors.append('INCOMPLETE_OR_INVALID_LANGUAGE_EVIDENCE')
    return dict(qualified=not errors,correct=correct and not errors and within,withinBudget=within,errors=errors,
                unexpectedInvoke=case['expected'] is None and response.get('draft',{}).get('status')=='invoke')
