package edu.sydney.probe;

public final class WorkflowTimingTest {
    private static int checks;
    private static void equal(long expected,long actual){checks++;if(expected!=actual)throw new AssertionError(expected+" != "+actual);}
    private static void timeout(long now,long deadline){
        checks++;
        try{WorkflowTiming.requireBeforeDeadline(now,deadline);throw new AssertionError("Expected timeout");}
        catch(IllegalStateException e){if(!"TASK_TIMEOUT".equals(e.getMessage()))throw e;}
    }
    private static void confirmationError(long now,long until,long deadline,String reason){
        checks++;
        try{WorkflowTiming.requireConfirmation(now,until,deadline);throw new AssertionError("Late confirmation accepted");}
        catch(IllegalStateException e){if(!reason.equals(e.getMessage()))throw e;}
    }
    public static void main(String[] args){
        // Five seconds spent observing before dispatch must not consume the
        // three-second post-dispatch window; the task deadline remains fixed.
        equal(8000,WorkflowTiming.confirmationDeadline(5000,30000));
        equal(30000,WorkflowTiming.confirmationDeadline(29000,30000));
        equal(3000,WorkflowTiming.confirmationDeadline(0,30000));
        equal(Long.MAX_VALUE,WorkflowTiming.confirmationDeadline(Long.MAX_VALUE-1000,Long.MAX_VALUE));
        timeout(30000,30000);timeout(31000,30000);
        WorkflowTiming.requireBeforeDeadline(29999,30000);checks++;
        if(WorkflowTiming.canReportSuccess(30000,30000))throw new AssertionError("Success at expired budget");checks++;
        if(WorkflowTiming.canReportSuccess(31000,30000))throw new AssertionError("Late success");checks++;
        if(!WorkflowTiming.canReportSuccess(29999,30000))throw new AssertionError("On-time finish");checks++;
        WorkflowTiming.requireConfirmation(6999,7000,30000);checks++;
        confirmationError(7000,7000,30000,"STEP_UNCONFIRMED");
        confirmationError(7001,7000,30000,"STEP_UNCONFIRMED");
        // A read may begin on time yet return late; its completed observation is decisive.
        confirmationError(8000,7000,30000,"STEP_UNCONFIRMED");
        confirmationError(30000,30000,30000,"TASK_TIMEOUT");
        confirmationError(31000,32000,30000,"TASK_TIMEOUT");
        WorkflowTiming.requireConfirmation(Long.MAX_VALUE-1,Long.MAX_VALUE,Long.MAX_VALUE);checks++;
        System.out.println("WorkflowTimingTest PASS checks="+checks);
    }
}
