package edu.sydney.probe;
public final class PrerequisiteAuditPolicyTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("readonly audit boundary");}
    public static void main(String[] args){
        String id="a".repeat(32);
        need(PrerequisiteAuditPolicy.accepts("edu.sydney.probe.PREREQUISITE_AUDIT",id));
        for(String bad:new String[]{"", "../x", "a".repeat(31), "a".repeat(33), "A".repeat(32), "z".repeat(32)})
            need(!PrerequisiteAuditPolicy.accepts("edu.sydney.probe.PREREQUISITE_AUDIT",bad));
        need(!PrerequisiteAuditPolicy.accepts(null,id));
        need(!PrerequisiteAuditPolicy.accepts("other",id));
        need(!PrerequisiteAuditPolicy.accepts("edu.sydney.probe.PREREQUISITE_AUDIT",null));
        System.out.println("PrerequisiteAuditPolicyTest: 10 checks passed");
    }
}
