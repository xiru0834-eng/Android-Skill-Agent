package edu.sydney.probe;

/** Final publication policy. Never turns an existing failure into success. */
final class FlowCompletionBoundary {
    static String status(String proposed,long finished,long deadline,boolean cancelled){
        if(!"SUCCESS".equals(proposed)&&!"NO_ACTION_REQUIRED".equals(proposed))return proposed;
        if(cancelled)return "CANCELLED";
        return finished>=deadline?"BUDGET_EXCEEDED":proposed;
    }
}
