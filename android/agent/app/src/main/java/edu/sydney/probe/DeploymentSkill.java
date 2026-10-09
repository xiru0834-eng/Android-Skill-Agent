package edu.sydney.probe;

import java.util.List;
import java.util.Locale;

/** Portable workflow provenance stays separate from a human-reviewed deployment. */
public final class DeploymentSkill {
    public final String workflowId,bindingId,parentBindingId,targetPackage;
    public final TwoStepSkill source;
    public final List<String> roles,targetIds;
    public DeploymentSkill(String workflowId,String bindingId,String parentBindingId,TwoStepSkill source,
                           List<String> roles,String targetPackage,List<String> targetIds) {
        if(!uuid(workflowId) || !uuid(bindingId) || parentBindingId==null
                || (!parentBindingId.isEmpty() && !uuid(parentBindingId)) || bindingId.equals(parentBindingId)
                || source==null || roles==null || roles.size()!=2 || targetIds==null || targetIds.size()!=2
                || !ProbePolicy.allowed(targetPackage)) throw new IllegalArgumentException("Invalid deployment");
        for(String role:roles) if(role==null || !role.equals(role.trim()) || role.isEmpty() || role.length()>64
                || role.chars().anyMatch(c->Character.isISOControl(c) || Character.getType(c)==Character.FORMAT))
            throw new IllegalArgumentException("Invalid role");
        if(roles.get(0).toLowerCase(Locale.ROOT).equals(roles.get(1).toLowerCase(Locale.ROOT)))
            throw new IllegalArgumentException("Distinct roles required");
        if(!BindingCatalog.validId(targetPackage,targetIds.get(0)) || !BindingCatalog.validId(targetPackage,targetIds.get(1))
                || targetIds.get(0).equals(targetIds.get(1))) throw new IllegalArgumentException("Distinct local IDs required");
        this.workflowId=workflowId;this.bindingId=bindingId;this.parentBindingId=parentBindingId;this.source=source;
        this.roles=List.copyOf(roles);this.targetPackage=targetPackage;this.targetIds=List.copyOf(targetIds);
    }
    private static boolean uuid(String value) { return value!=null && value.matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"); }
    /** Execution-only adapter. These synthetic before values are NEVER exported as target demonstrations. */
    TwoStepSkill boundSkill() {
        boolean a=source.steps.get(0).defaultDesired,b=source.steps.get(1).defaultDesired;
        return new TwoStepSkill(List.of(new SwitchSkill(targetPackage,targetIds.get(0),!a,a),new SwitchSkill(targetPackage,targetIds.get(1),!b,b)));
    }
}
