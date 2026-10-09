package edu.sydney.probe;
import java.util.*;

/** Additive public parameter outcome; legacy status/reason remain unchanged. */
final class ParameterOutcome {
    private static final Set<String> ENTRY_CODES=Set.of("UNSUPPORTED_VALUE","PARAMETER_INTEGER","PERCENT_RANGE","POWER_STATE","UNKNOWN_ENTITY","UNBOUND_DEVICE","UNBOUND_CAPABILITY",
        "CALL_COUNT","ARGUMENT_FIELDS","UNKNOWN_SKILL","VALUE_TYPE","VALUE_RANGE","VALUE_ENUM","DEVICE_TYPE","RESPONSE_MISMATCH","UNEXPECTED_CALLS","STATUS",
        "PARAMETER_BINDING_CHANGED","NO_PARAMETER_SOURCE","STORAGE_UNCONFIRMED","STALE_CONFIRMATION","SELECTION_CHANGED","SELECTION_DEADLINE","REMOTE_BUSY","SERVICE_OFF","CAPABILITY","ENTRY_INVALID","ENTRY_UNAVAILABLE","MODEL_REJECTED","CLARIFICATION_REQUIRED");
    static String safeEntryReason(String raw){return ENTRY_CODES.contains(String.valueOf(raw))?raw:"ENTRY_INVALID";}
    static String entryReason(String raw,boolean validationException,String fallbackStage){
        String reason=safeEntryReason(raw);
        if(reason.equals("ENTRY_INVALID")&&(!validationException||
            ("parsing".equals(fallbackStage)&&String.valueOf(raw).matches("BRIDGE_HTTP_[0-9]{3}"))))reason="ENTRY_UNAVAILABLE";
        return reason;
    }
    static String entryStatus(String reason){return Set.of("SELECTION_DEADLINE","REMOTE_BUSY","SERVICE_OFF","STALE_CONFIRMATION","SELECTION_CHANGED","CLARIFICATION_REQUIRED","ENTRY_UNAVAILABLE").contains(reason)?"UNCONFIRMED":"REJECTED";}
    static boolean canFinish(boolean allCallsAlreadySatisfied,boolean legacyProcessComplete,boolean freshStateMatches,boolean finalTargetsMatch){
        return (allCallsAlreadySatisfied||legacyProcessComplete)&&freshStateMatches&&finalTargetsMatch;
    }
    static String status(String legacy,String reason,int inputs){
        if("SUCCEEDED".equals(legacy))return inputs==0?"NO_ACTION_REQUIRED":"SUCCESS";
        if("REJECTED".equals(legacy))return inputs==0?"REJECTED":"UNCONFIRMED";
        if(Set.of("WRONG_APP","WRONG_PAGE","INVALID_START","STEP_PRECONDITION_CHANGED","FINAL_TARGET_MISMATCH","UNTOUCHED_TARGET_CHANGED").contains(String.valueOf(reason)))return "FAILED";
        return "UNCONFIRMED";
    }
    static String stage(String reason,int phase){
        String r=String.valueOf(reason);
        if(Set.of("RESPONSE_MISMATCH","STATUS","UNKNOWN_SKILL","ARGUMENT_FIELDS","UNEXPECTED_CALLS","SELECTION_DEADLINE","REMOTE_BUSY","SELECTION_CHANGED","MODEL_REJECTED","CLARIFICATION_REQUIRED").contains(r))return "parsing";
        if(Set.of("VALUE_RANGE","VALUE_TYPE","VALUE_ENUM","PERCENT_RANGE","PARAMETER_INTEGER","UNSUPPORTED_VALUE","POWER_STATE","UNKNOWN_ENTITY","DEVICE_TYPE","CALL_COUNT","ENTRY_INVALID").contains(r))return "validation";
        if("INPUT_REJECTED".equals(r))return "execution";
        if(r.startsWith("MISSING:")||r.startsWith("AMBIGUOUS:")||r.startsWith("STALE:")||r.startsWith("UNUSABLE:")
            ||Set.of("WRONG_APP","WRONG_PAGE","NOT_CLICKABLE","NOT_CHECKABLE","TARGET_NOT_VISIBLE","STEP_PRECONDITION_CHANGED","INVALID_START","PARAMETER_BINDING_CHANGED","APPROVAL_CHANGED","UNBOUND_CAPABILITY","UNBOUND_DEVICE","TARGET_CONTEXT_CHANGED","NO_PARAMETER_SOURCE","STORAGE_UNCONFIRMED","SERVICE_OFF","STALE_CONFIRMATION","CAPABILITY").contains(r))return "binding";
        if(Set.of("STEP_UNCONFIRMED","FINAL_TARGET_MISMATCH","UNTOUCHED_TARGET_CHANGED","INVALID_SUMMARY","INVALID_SELECTION","PAGE_CHANGED").contains(r))return "verification";
        return phase==2||phase==3?"verification":"execution";
    }
}
