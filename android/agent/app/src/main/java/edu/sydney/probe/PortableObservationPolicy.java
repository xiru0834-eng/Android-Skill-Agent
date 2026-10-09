package edu.sydney.probe;

/** Only explicit transient observation faults may be retried; never an input. */
final class PortableObservationPolicy {
    static boolean retryObservation(String reason){return reason!=null&&(reason.startsWith("STALE")||reason.equals("PAGE_LOADING"));}
    static String failureStatus(String stage,String reason){
        if(stage.equals("validation"))return "REJECTED";
        if(reason.equals("NO_TREE")||reason.equals("ROOT_READ_FAILED")||reason.equals("SERVICE_UNAVAILABLE")||reason.equals("LAUNCH_WINDOW_UNAVAILABLE"))return "ENVIRONMENT_ERROR";
        if(reason.equals("BLOCKED_BY_OVERLAY"))return "BLOCKED_BY_OVERLAY";
        if(reason.startsWith("AMBIGUOUS"))return "AMBIGUOUS";
        if(reason.contains("DEADLINE")||reason.equals("TASK_TIMEOUT")||reason.equals("CANCELLED")||retryObservation(reason)||stage.equals("verification"))return "UNCONFIRMED";
        return stage.equals("resolution")?"UNRESOLVED":"FAILED";
    }
}
