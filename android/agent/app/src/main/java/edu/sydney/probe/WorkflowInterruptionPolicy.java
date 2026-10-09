package edu.sydney.probe;
/** A reconnected service closes orphan checkpoints; it never resumes them. */
final class WorkflowInterruptionPolicy {
    private WorkflowInterruptionPolicy(){}
    static boolean execution(String state,boolean live){return !live&&"RUNNING".equals(state);}
    static boolean recording(String state,boolean live){return !live&&"RECORDING".equals(state);}
    static boolean validId(String id){return id!=null&&id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");}
}
