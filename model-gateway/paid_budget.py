"""Per-authorization experiment ledger; unknown bills keep their worst-case reserve.

New file only: no silent resume/reset of authorization. One instance owns the file.
Not the provider invoice; rates and FX guard are frozen conservative assumptions.
"""
import copy
import json
import os
from pathlib import Path
import threading
from compiler import MODEL, ModelError


class PaidBudget:
    def __init__(self,path,max_calls=200,max_nano_usd=2_000_000_000,*,request_profile='legacy'):
        profiles={'legacy':(300,32768),'semantic-v2':(4096,65536)}
        if type(request_profile) is not str or request_profile not in profiles:raise ValueError('REQUEST_PROFILE')
        if type(max_calls) is not int or not 1<=max_calls<=200:raise ValueError('CALL_LIMIT')
        if type(max_nano_usd) is not int or not 0<max_nano_usd<=2_000_000_000:raise ValueError('MONEY_LIMIT')
        # A new authorisation can opt into semantic requests. Existing ledgers
        # cannot be reopened or silently upgraded, and the default stays legacy.
        self.output_cap,self.byte_cap=profiles[request_profile]
        self.path=Path(path);self.lock=threading.Lock()
        self.data=dict(requestProfile=request_profile,requestMaxOutputTokens=self.output_cap,requestMaxBytes=self.byte_cap,
            maxCalls=max_calls,maxNanoUsd=max_nano_usd,cnyPerUsdGuard=10,
            inputNanoUsdPerToken=2750,outputNanoUsdPerToken=11000,attempts=0,
            exposureNanoUsd=0,halted=False,rows=[])
        with self.path.open('x',encoding='utf-8') as handle:self._dump(handle)

    def _dump(self,handle):
        json.dump(self.data,handle,ensure_ascii=True,indent=2);handle.flush();os.fsync(handle.fileno())

    def _save(self):
        temporary=self.path.with_suffix('.pending')
        with temporary.open('x',encoding='utf-8') as handle:self._dump(handle)
        os.replace(temporary,self.path)

    def snapshot(self):
        with self.lock:return copy.deepcopy(self.data)

    def call(self,body,timeout,remote):
        request=copy.deepcopy(body)
        allowed={'model','store','reasoning','temperature','max_output_tokens','input','text','service_tier'}
        if (not isinstance(request,dict) or set(request)-allowed or request.get('model')!=MODEL
            or request.get('store') is not False or request.get('reasoning')!={'effort':'none'}
            or request.get('service_tier','default')!='default'
            or type(request.get('max_output_tokens')) is not int or not 1<=request['max_output_tokens']<=self.output_cap
            or not isinstance(request.get('input'),list) or not 1<=len(request['input'])<=2
            or any(not isinstance(v,dict) or set(v)!={'role','content'}
                   or v['role'] not in ('system','user') or not isinstance(v['content'],str) for v in request['input'])):
            raise ModelError('PAID_REQUEST_POLICY')
        request['service_tier']='default'
        size=len(json.dumps(request,ensure_ascii=False).encode('utf-8'))
        if size>self.byte_cap:raise ModelError('PAID_REQUEST_POLICY')
        input_bound=size+4096;output_bound=request['max_output_tokens']
        reserve=input_bound*2750+output_bound*11000
        with self.lock:
            if self.data['halted']:raise ModelError('PAID_HALTED')
            if self.data['attempts']>=self.data['maxCalls']:raise ModelError('PAID_CALL_CAP')
            if self.data['exposureNanoUsd']+reserve>self.data['maxNanoUsd']:raise ModelError('PAID_MONEY_CAP')
            row=dict(index=self.data['attempts'],state='UNKNOWN_RESERVED',nanoUsd=reserve,
                     inputBound=input_bound,outputBound=output_bound)
            self.data['rows'].append(row);self.data['attempts']+=1;self.data['exposureNanoUsd']+=reserve
            self._save()  # Write-ahead: even a send failure consumes this authorization.
        try:
            response=remote(request,timeout=timeout)
            with self.lock:
                if not isinstance(response,dict) or response.get('returned_model')!=MODEL:
                    self.data['halted']=True;self._save();raise ModelError('PAID_RESPONSE_POLICY')
                counts=[response.get(k) for k in ('input_tokens','output_tokens')]
                if all(type(v) is int and v>=0 for v in counts) and counts[0]>0:
                    if counts[0]>input_bound or counts[1]>output_bound:
                        self.data['halted']=True;self._save();raise ModelError('PAID_RESPONSE_POLICY')
                    cost=counts[0]*2750+counts[1]*11000
                    self.data['exposureNanoUsd']+=cost-reserve
                    row.update(state='SETTLED',nanoUsd=cost,inputTokens=counts[0],outputTokens=counts[1])
                self._save()
            return response
        except Exception:
            # Never return authorization on failure; no retry and no zero-cost guess.
            raise
