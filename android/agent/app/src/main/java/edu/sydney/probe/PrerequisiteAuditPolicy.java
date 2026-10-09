package edu.sydney.probe;
/** Fixed read-only diagnostic contract; no caller-controlled package, path or operation. */
final class PrerequisiteAuditPolicy {
    static final String ACTION="edu.sydney.probe.PREREQUISITE_AUDIT";
    static boolean accepts(String action,String id){return ACTION.equals(action)&&id!=null&&id.matches("[a-f0-9]{32}");}
}
