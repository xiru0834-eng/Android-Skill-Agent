package edu.sydney.probe;

public final class WorkflowStartupTest {
    private static int checks;
    private static void check(boolean ok){checks++;if(!ok)throw new AssertionError("check "+checks);}
    private static WorkflowStartup gate(){return new WorkflowStartup(1000,31000);}
    public static void main(String[] args){
        WorkflowStartup g=gate();
        check(g.until()==9000);
        check(g.canRetry(5500,"WRONG_APP","CONTROLLER")); // old 4s allowance ends at 5000
        check(!g.ready(5500,"overview-A"));
        check(!g.ready(5599,"overview-A"));
        check(g.ready(5600,"overview-A"));
        g=gate();check(!g.ready(2000,"overview-A"));check(!g.ready(2100,"overview-B"));
        check(g.ready(2200,"overview-B"));
        g=gate();check(!g.ready(2000,"overview-A"));g.interrupted();check(!g.ready(2200,"overview-A"));
        check(g.canRetry(8999,"WRONG_APP","NONE"));check(!g.canRetry(9000,"WRONG_APP","NONE"));
        check(!g.canRetry(2000,"WRONG_APP","OTHER"));check(!g.canRetry(2000,"INVALID_START","TARGET"));
        check(!g.canRetry(2000,"AMBIGUOUS:wfPage","TARGET"));
        check(g.canRetry(2000,"NOT_READY","TARGET"));
        check(!g.canRetry(2000,"APPROVAL_CHANGED","CONTROLLER"));
        check(!g.canRetry(31000,"WRONG_APP","NONE"));check(!g.ready(9000,"overview-A"));
        check(new WorkflowStartup(1000,24000).until()==2000); // reserve 22s, no reset of budget
        check(!new WorkflowStartup(1000,23000).ready(1000,"overview-A"));
        // Unknown errors/root kinds never acquire retry permission.
        check(!gate().canRetry(2000,"MISSING:wfPage","TARGET"));
        check(!gate().canRetry(2000,"WRONG_APP","UNKNOWN"));
        // The v14/B0 phase-0 schedule: first poll 900ms, then 100ms,
        // retry on failure only while elapsed <4000. Compare a controlled handoff.
        check(!baselineCanReach(4500));
        check(candidateCanReach(4500,"CONTROLLER"));
        check(candidateCanReach(4500,"NONE"));
        check(!candidateCanReach(4500,"OTHER"));
        check(baselineCanReach(900));check(candidateCanReach(900,"CONTROLLER"));
        check(!candidateCanReach(7900,"CONTROLLER")); // cannot fit the second observation
        check(!candidateCanReach(9000,"CONTROLLER"));
        check(WorkflowStartup.invalidStart(0,"INVALID_START"));
        check(!WorkflowStartup.invalidStart(1,"INVALID_START"));
        check(!WorkflowStartup.invalidStart(0,"WRONG_APP"));
        check(!WorkflowStartup.invalidStart(0,"NOT_READY"));
        check(!WorkflowStartup.invalidStart(0,null));
        System.out.println("WorkflowStartupTest PASS checks="+checks);
    }
    private static boolean baselineCanReach(long targetAt){
        for(long now=900;now<=4000;now+=100)if(now>=targetAt)return true;
        return false;
    }
    private static boolean candidateCanReach(long targetAt,String priorRoot){
        WorkflowStartup gate=new WorkflowStartup(0,30000);
        for(long now=900;now<30000;now+=100){
            if(now>=gate.until())return false;
            if(now>=targetAt){if(gate.ready(now,"clean-overview"))return true;}
            else{gate.interrupted();if(!gate.canRetry(now,"WRONG_APP",priorRoot))return false;}
        }
        return false;
    }
}
