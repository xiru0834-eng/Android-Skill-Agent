package edu.sydney.probe;
/** Preserve existing recovery/diagnostic codes at the Android resolver boundary. */
final class WorkflowResolutionReason {
    static String translate(String reason,String id){
        if("MISSING_TARGET".equals(reason))return "MISSING:"+id;
        if("AMBIGUOUS_ID".equals(reason)||"AMBIGUOUS_TARGET".equals(reason))return "AMBIGUOUS:"+id;
        if("TARGET_DISABLED".equals(reason))return "NOT_CLICKABLE";
        if("UNUSABLE_TARGET".equals(reason))return "UNUSABLE:"+id;
        return reason;
    }
}
