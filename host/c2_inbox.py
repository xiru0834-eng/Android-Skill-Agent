"""Durable candidate inbox, not a second publication store or execution authority."""
import json,re,sqlite3
from contextlib import contextmanager
from pathlib import Path
from c2_material import canonical,digest,contracts

def valid_id(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('REQUEST_ID')
    return value

class DraftInbox:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,state TEXT NOT NULL,name TEXT,body TEXT NOT NULL,digest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY CHECK(id=1),reserved INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO budget VALUES(1,0)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()
    def _read(self,db,id):
        row=db.execute('SELECT state,name,body,digest FROM drafts WHERE id=?',(valid_id(id),)).fetchone()
        if row is None:raise ValueError('NOT_FOUND')
        body=json.loads(row[2])
        if digest(body)!=row[3]:raise ValueError('DRAFT_CORRUPT')
        return {'id':id,'state':row[0],'name':row[1],'body':body,'execution_authority':False}
    def _write(self,db,id,state,body,name=None):
        text=canonical(body)
        if len(text.encode())>1048576:raise ValueError('DRAFT_SIZE_LIMIT')
        db.execute('UPDATE drafts SET state=?,name=?,body=?,digest=? WHERE id=?',(state,name,text,digest(body),id))
    def begin(self,id,material):
        valid_id(id);text=canonical(material)
        if len(text.encode())>1048576:raise ValueError('MATERIAL_SIZE_LIMIT')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]>=64:raise ValueError('SESSION_LIMIT')
            try:db.execute('INSERT INTO drafts VALUES(?,?,?,?,?)',(id,'GENERATING',None,text,digest(material)))
            except sqlite3.IntegrityError:raise ValueError('DUPLICATE_REQUEST') from None
    def inspect(self,id):
        with self.connect() as db:return self._read(db,id)
    def complete(self,id,result):
        if type(result) is not dict or result.get('execution_authority',False) is not False:raise ValueError('DRAFT_AUTHORITY')
        contracts.validate_document(result.get('candidate_flow'))
        if result['candidate_flow'].get('verified_scope')!=[]:raise ValueError('DRAFT_ONLY')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._read(db,id)
            if old['state']!='GENERATING':raise ValueError('CANCELLED_OR_STALE')
            self._write(db,id,'DRAFT',{'material':old['body'],'generation':result})
        return self.inspect(id)
    def fail(self,id,code):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._read(db,id)
            if old['state']=='GENERATING':self._write(db,id,'FAILED',{'material':old['body'],'failure':code})
    def needs_material(self,id,result):
        if (type(result) is not dict or result.get('execution_authority') is not False or result.get('ready_for_device_execution') is not False
            or result.get('candidate_flow') is not None or not result.get('questions')):raise ValueError('GAP_RESULT_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._read(db,id)
            if old['state']!='GENERATING':raise ValueError('CANCELLED_OR_STALE')
            self._write(db,id,'NEEDS_MATERIAL',{'material':old['body'],'generation':result})
        return self.inspect(id)
    def cancel(self,id):
        valid_id(id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM drafts WHERE id=?',(id,)).fetchone() is None:
                if db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]>=64:raise ValueError('SESSION_LIMIT')
                body={'reason':'CANCELLED_BEFORE_START','execution_authority':False}
                db.execute('INSERT INTO drafts VALUES(?,?,?,?,?)',(id,'CANCELLED',None,canonical(body),digest(body)))
            old=self._read(db,id)
            if old['state']=='GENERATING':self._write(db,id,'CANCELLED',old['body'])
        return self.inspect(id)
    def name(self,id,name):
        if type(name) is not str or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):raise ValueError('NAME_INVALID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self._read(db,id)
            if old['state']!='DRAFT':raise ValueError('NOT_A_DRAFT')
            self._write(db,id,'DRAFT',old['body'],name.strip())
        return self.inspect(id)
    def reserve(self,calls,*,limit):
        if type(calls) is not int or calls<1:raise ValueError('MODEL_LIMIT')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');used=db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
            if used+calls>limit:raise ValueError('MODEL_LIMIT')
            db.execute('UPDATE budget SET reserved=? WHERE id=1',(used+calls,))
