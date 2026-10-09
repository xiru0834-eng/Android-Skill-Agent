"""Local append-only evidence; atomic revisions and a physically read-only query connection."""
import json
from pathlib import Path
import sqlite3
import threading

from bundle_contract import BundleError,need,environment,validate_bundle
from p24deps import canonical,digest


class BundleStore:
    def __init__(self,path,*,create=False,read_only=False,max_payload_bytes=16*1024*1024):
        need(type(create) is bool and type(read_only) is bool and not (create and read_only),'INVALID_STORE_MODE')
        need(type(max_payload_bytes) is int and 0<max_payload_bytes<=64*1024*1024,'INVALID_STORE_LIMIT')
        need(isinstance(path,(str,Path)),'INVALID_STORE_PATH')
        self.path=Path(path).absolute()
        need(self.path.suffix=='.sqlite' and self.path.parent.is_dir(),'INVALID_STORE_PATH')
        self.read_only=read_only;self.max_payload_bytes=max_payload_bytes;self.lock=threading.RLock()
        existed=self.path.exists();need(existed or create,'STORE_NOT_FOUND')
        self.con=None
        try:
            uri=self.path.as_uri()+('?mode=ro' if read_only else '?mode=rw') if existed else str(self.path)
            self.con=sqlite3.connect(uri,uri=existed,isolation_level=None,timeout=0.5,check_same_thread=False)
            if not existed:
                self.con.executescript('''BEGIN IMMEDIATE;
                    CREATE TABLE metadata(version TEXT NOT NULL, revision INTEGER NOT NULL);
                    INSERT INTO metadata VALUES('p24.1',0);
                    CREATE TABLE bundles(revision INTEGER PRIMARY KEY, bundle_id TEXT UNIQUE NOT NULL,
                                         env_key TEXT NOT NULL, payload TEXT NOT NULL, payload_digest TEXT NOT NULL);
                    COMMIT;''')
            tables={r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            need(tables=={'metadata','bundles'},'FOREIGN_STORE')
            metadata=self.con.execute('SELECT version,revision FROM metadata').fetchall()
            need(len(metadata)==1 and metadata[0][0]=='p24.1' and type(metadata[0][1]) is int and metadata[0][1]>=0,
                 'STORE_SCHEMA_INCOMPATIBLE')
            need(self.con.execute('PRAGMA quick_check').fetchone()[0]=='ok','STORE_CORRUPT')
            self.con.execute('SELECT revision,bundle_id,env_key,payload,payload_digest FROM bundles LIMIT 0')
        except Exception as error:
            if self.con:self.con.close()
            if isinstance(error,sqlite3.Error):raise BundleError('STORE_CORRUPT') from error
            raise

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):self.con.close()

    def revision(self):
        with self.lock:
            try:return self.con.execute('SELECT revision FROM metadata').fetchone()[0]
            except (sqlite3.Error,TypeError) as error:raise BundleError('STORE_CORRUPT') from error

    def _rows(self):
        used=self.con.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM bundles').fetchone()[0]
        need(used<=self.max_payload_bytes,'STORAGE_CAPACITY')
        rows=self.con.execute('SELECT revision,bundle_id,env_key,payload,payload_digest FROM bundles ORDER BY revision').fetchall()
        need(len(rows)<=4096,'STORE_RECORD_LIMIT')
        values=[]
        for i,(rev,bid,env,encoded,sha) in enumerate(rows,1):
            need(rev==i,'STORE_REVISION_ERROR')
            try:b=validate_bundle(json.loads(encoded))
            except (ValueError,TypeError) as error:raise BundleError('STORE_CORRUPT') from error
            need(digest(b)==sha and bid==b['bundle_id'] and env==digest(b['environment']),'STORE_DIGEST_ERROR')
            values.append({'record_revision':rev,'bundle':b,'sha256':sha})
        need(len(values)==self.revision(),'STORE_REVISION_ERROR')
        return values

    def append(self,value,*,expected_revision,fail_before_commit=False):
        need(not self.read_only,'STORE_READ_ONLY')
        need(type(expected_revision) is int and expected_revision>=0 and type(fail_before_commit) is bool,'INVALID_REVISION')
        b=validate_bundle(value);payload=canonical(b)
        with self.lock:
            try:
                self.con.execute('BEGIN IMMEDIATE');rows=self._rows()
                need(self.revision()==expected_revision,'REVISION_CONFLICT')
                need(all(r['bundle']['bundle_id']!=b['bundle_id'] for r in rows),'DUPLICATE_BUNDLE')
                need(len(rows)<4096,'STORE_RECORD_LIMIT')
                used=sum(len(canonical(r['bundle']).encode('utf-8')) for r in rows)
                need(used+len(payload.encode('utf-8'))<=self.max_payload_bytes,'STORAGE_CAPACITY')
                revision=expected_revision+1
                self.con.execute('INSERT INTO bundles VALUES(?,?,?,?,?)',
                                 (revision,b['bundle_id'],digest(b['environment']),payload,digest(b)))
                self.con.execute('UPDATE metadata SET revision=?',(revision,))
                need(not fail_before_commit,'STORAGE_INTERRUPTION')
                self.con.execute('COMMIT')
                return {'bundle_id':b['bundle_id'],'memory_revision':revision,'execution_authority':False}
            except Exception as error:
                if self.con.in_transaction:self.con.execute('ROLLBACK')
                if isinstance(error,sqlite3.Error):raise BundleError('STORAGE_ERROR') from error
                raise

    def snapshot(self,env,*,expected_revision=None):
        target=environment(env)
        need(expected_revision is None or type(expected_revision) is int and expected_revision>=0,'INVALID_REVISION')
        with self.lock:
            try:
                self.con.execute('BEGIN');revision=self.revision()
                need(expected_revision is None or expected_revision==revision,'REVISION_CONFLICT')
                rows=self._rows()
                return {'environment':target,'memory_revision':revision,
                        'bundles':[r for r in rows if r['bundle']['environment']==target],
                        'execution_authority':False,'current_ui_confirmed':False}
            except sqlite3.Error as error:raise BundleError('STORE_CORRUPT') from error
            finally:
                if self.con.in_transaction:self.con.execute('ROLLBACK')
