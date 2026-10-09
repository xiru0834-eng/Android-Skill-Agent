package edu.sydney.probe;

/** A read-only, non-sliding allowance before an input, never a replay permit. */
final class WorkflowRecovery {
    private long until;
    private String target;
    void clear(){until=0;target=null;}
    long until(){return until;}
    boolean active(){return target!=null;}
    boolean retryStale(long now,long deadline,int phase,String reason){
        return active()&&phase==1&&reason!=null&&reason.startsWith("STALE:")&&now<until&&now<deadline-3500;
    }
    boolean waitFor(long now,long deadline,int phase,String id,String reason){
        if(phase!=1||id==null||!("MISSING:"+id).equals(reason)||now>=deadline-3500)return false;
        if(target==null){target=id;until=Math.min(now+1500,deadline-3500);}
        return target.equals(id)&&now<until;
    }
}
