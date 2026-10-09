package edu.sydney.probe;

public final class WorkflowRecoveryTest {
    private static int checks;
    private static void check(boolean value){checks++;if(!value)throw new AssertionError("check "+checks);}
    public static void main(String[] args){
        WorkflowRecovery r=new WorkflowRecovery();
        check(r.waitFor(1000,30000,1,"wfFanSave","MISSING:wfFanSave"));
        check(r.until()==2500);
        check(r.waitFor(2400,30000,1,"wfFanSave","MISSING:wfFanSave"));
        check(r.until()==2500); // repeated errors must not reset the clock
        check(!r.waitFor(2500,30000,1,"wfFanSave","MISSING:wfFanSave"));
        r.clear();
        check(!r.waitFor(27000,30000,1,"wfFanSave","MISSING:wfFanSave"));
        r.clear();
        check(r.waitFor(26000,30000,1,"wfFanSave","MISSING:wfFanSave"));
        check(r.until()==26500);
        for(String reason:new String[]{"AMBIGUOUS:wfFanSave","WRONG_PAGE","WRONG_APP","NOT_READY","APPROVAL_CHANGED","MISSING:wfPage","UNUSABLE:wfFanSave"}){
            r.clear();check(!r.waitFor(1000,30000,1,"wfFanSave",reason));
        }
        for(int phase:new int[]{0,2,3}){r.clear();check(!r.waitFor(1000,30000,phase,"wfFanSave","MISSING:wfFanSave"));}
        r.clear();check(r.waitFor(1000,30000,1,"a","MISSING:a"));
        check(!r.waitFor(1100,30000,1,"b","MISSING:b")); // cannot transfer a live allowance
        r.clear();check(r.waitFor(2000,30000,1,"b","MISSING:b"));
        check(r.until()==3500);
        check(!r.waitFor(30000,30000,1,"b","MISSING:b"));
        r.clear();check(!r.retryStale(1000,30000,1,"STALE:wfFanDirty"));
        check(r.waitFor(1000,30000,1,"wfFanSave","MISSING:wfFanSave"));
        check(r.retryStale(1800,30000,1,"STALE:wfFanDirty"));
        check(r.until()==2500);
        check(!r.retryStale(2500,30000,1,"STALE:wfFanDirty"));
        check(!r.retryStale(1800,30000,2,"STALE:wfFanDirty"));
        check(!r.retryStale(1800,30000,1,"UNUSABLE:wfFanDirty"));
        check(!r.retryStale(1800,30000,1,"WRONG_APP"));
        System.out.println("WorkflowRecoveryTest "+checks+" checks passed");
    }
}
