package edu.sydney.probe;
public final class PortableObservationPolicyTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("observation policy");}
    public static void main(String[] args){
        need(PortableObservationPolicy.failureStatus("resolution","NO_TREE").equals("ENVIRONMENT_ERROR"));
        need(PortableObservationPolicy.failureStatus("resolution","LAUNCH_WINDOW_UNAVAILABLE").equals("ENVIRONMENT_ERROR"));
        need(PortableObservationPolicy.failureStatus("verification","ROOT_READ_FAILED").equals("ENVIRONMENT_ERROR"));
        need(PortableObservationPolicy.failureStatus("execution","BLOCKED_BY_OVERLAY").equals("BLOCKED_BY_OVERLAY"));
        need(PortableObservationPolicy.failureStatus("resolution","STALE_TREE").equals("UNCONFIRMED"));
        need(PortableObservationPolicy.failureStatus("resolution","TASK_TIMEOUT").equals("UNCONFIRMED"));
        need(PortableObservationPolicy.failureStatus("resolution","WRONG_APP").equals("UNRESOLVED"));
        need(PortableObservationPolicy.failureStatus("validation","NO_TREE").equals("REJECTED"));
        need(PortableObservationPolicy.retryObservation("STALE:brightness"));
        need(PortableObservationPolicy.retryObservation("PAGE_LOADING"));
        for(String reason:new String[]{"NO_TREE","ROOT_READ_FAILED","BLOCKED_BY_OVERLAY","NOT_FOUND","AMBIGUOUS_TARGET","INPUT_REJECTED","CANCELLED","TARGET_STATE_CHANGED"})need(!PortableObservationPolicy.retryObservation(reason));
        System.out.println("PortableObservationPolicyTest: 17 checks passed");
    }
}
