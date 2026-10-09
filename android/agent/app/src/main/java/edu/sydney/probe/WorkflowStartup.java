package edu.sydney.probe;

/** Bounded observation-only handoff. Repeated observations are consistency, not freshness proof. */
final class WorkflowStartup {
    private final long until;
    private String previous;
    private long firstSeen;
    WorkflowStartup(long started,long deadline){
        if(started<0||deadline<started)throw new IllegalArgumentException("STARTUP_CLOCK");
        until=started+Math.min(8000,Math.max(0,deadline-started-22000));
    }
    long until(){return until;}
    static boolean invalidStart(int phase,String reason){return phase==0&&"INVALID_START".equals(reason);}
    void interrupted(){previous=null;}
    boolean ready(long now,String state){
        if(now>=until||state==null){interrupted();return false;}
        if(!state.equals(previous)){previous=state;firstSeen=now;return false;}
        return now-firstSeen>=100;
    }
    boolean canRetry(long now,String reason,String rootKind){
        if(now>=until)return false;
        if("WRONG_APP".equals(reason))return "NONE".equals(rootKind)||"CONTROLLER".equals(rootKind);
        return "NOT_READY".equals(reason)&&"TARGET".equals(rootKind);
    }
}
