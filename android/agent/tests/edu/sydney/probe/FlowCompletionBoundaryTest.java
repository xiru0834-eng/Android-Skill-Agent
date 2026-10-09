package edu.sydney.probe;
public final class FlowCompletionBoundaryTest {
    static void need(String actual,String wanted){if(!actual.equals(wanted))throw new AssertionError(actual+" != "+wanted);}
    public static void main(String[] args){
        need(FlowCompletionBoundary.status("SUCCESS",7999,8000,false),"SUCCESS");
        need(FlowCompletionBoundary.status("SUCCESS",8000,8000,false),"BUDGET_EXCEEDED");
        need(FlowCompletionBoundary.status("SUCCESS",8013,8000,false),"BUDGET_EXCEEDED");
        need(FlowCompletionBoundary.status("NO_ACTION_REQUIRED",8001,8000,false),"BUDGET_EXCEEDED");
        need(FlowCompletionBoundary.status("SUCCESS",7999,8000,true),"CANCELLED");
        need(FlowCompletionBoundary.status("UNCONFIRMED",9000,8000,false),"UNCONFIRMED");
        need(FlowCompletionBoundary.status("CANCELLED",7999,8000,false),"CANCELLED");
        System.out.println("PASS FlowCompletionBoundaryTest late success/no-op blocked; original failure/cancel retained");
    }
}
