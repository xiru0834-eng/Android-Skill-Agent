"""Selection deadline and local revocation; never issues phone input."""
import copy
import math
import threading
import time
from compiler import ModelError
from selection_accuracy import select_accuracy
from skill_selection import select_skill

_NETWORK_POOL=threading.BoundedSemaphore(2)


class SelectionBudget:
    """One monotonic budget, local revocation, and bounded outstanding network work.

    A cancelled request may still incur provider charges. Its late result cannot
    re-enter the caller or start a second request. Callbacks must be thread-safe.
    """
    def __init__(self,seconds,cancelled=lambda:False,is_current=lambda:True,
                 clock=time.monotonic,pool=_NETWORK_POOL,max_calls=2):
        if type(seconds) not in (float,int) or not math.isfinite(seconds) or not 0<seconds<=45:
            raise ValueError('INVALID_BUDGET')
        if type(max_calls) is not int or max_calls not in (1,2):raise ValueError('INVALID_CALL_CAP')
        self.clock=clock;self.seconds=seconds;self.deadline=clock()+seconds
        self.cancelled=cancelled;self.is_current=is_current;self.pool=pool
        self.max_calls=max_calls;self.calls=[]

    def check(self):
        if self.cancelled():raise ModelError('SELECTION_CANCELLED')
        if not self.is_current():raise ModelError('STALE_REQUEST')
        remaining=self.deadline-self.clock()
        if remaining<=0:raise ModelError('SELECTION_DEADLINE')
        # Large absolute clock values can round deadline-start slightly upward.
        # Never pass a transport a timeout greater than the configured interval.
        return min(self.seconds,remaining)

    def call(self,transport,body,provider):
        remaining=self.check()
        if len(self.calls)>=self.max_calls:raise ModelError('PER_REQUEST_CAP')
        request=copy.deepcopy(body)
        if not self.pool.acquire(False):raise ModelError('REMOTE_BUSY')
        started=self.clock();ready=threading.Event();returned=[];errors=[]
        # Snapshot caller data before crossing the thread boundary.
        record=dict(provider=provider,timeoutSeconds=remaining,outcome='PENDING',request=request)
        self.calls.append(record)
        def worker():
            try:
                self.check()
                returned.append(transport(request,timeout=self.check()))
            except Exception as error:errors.append(error)
            finally:self.pool.release();ready.set()
        try:
            try:threading.Thread(target=worker,daemon=True,name='selection-network').start()
            except Exception:
                self.pool.release()
                raise
            while not ready.wait(min(.02,self.check())):pass
            self.check()  # A completed but late/revoked response is still unusable.
            if errors:raise errors[0]
            record['outcome']='RETURNED'
            record['response']=returned[0]
            return returned[0]
        except Exception as error:
            record['outcome']=str(error) if isinstance(error,ModelError) else type(error).__name__
            raise
        finally:record['elapsedMs']=round((self.clock()-started)*1000,4)


def select_bounded(strategy,text,skills,budget,jev_transport=None,gpt_transport=None):
    """Keep old H semantics while wrapping all calls and final delivery in one budget."""
    from deadline_remote import jev_remote,gpt_remote
    if strategy not in ('G','H2'):raise ValueError('INVALID_STRATEGY')
    budget.check();catalog=copy.deepcopy(skills)
    def jev(body):return budget.call(jev_transport or jev_remote,body,'Jev')
    def gpt(body):return budget.call(gpt_transport or gpt_remote,body,'GPT')
    result=select_skill(text,catalog,gpt) if strategy=='G' else select_accuracy(text,catalog,jev,gpt,review=True)
    budget.check()
    return result
