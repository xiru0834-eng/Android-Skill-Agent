package edu.sydney.probe;

/** Task-level counters; re-observation never resets the action/time budget. No Android handles. */
final class LearningScope {
    static final int MAX_ACTIONS=8,MAX_CAPTURES=64,MAX_EVENTS=256;
    static final long TOTAL_MS=120_000,OBSERVATION_TTL_MS=2_000;
    final String id,pkg;final long started;int actions,captures;
    private String observation;private long observedAt;private boolean cancelled;
    LearningScope(String id,String pkg,long started){
        if(!validId(id)||!allowedPackage(pkg))throw new IllegalStateException("INVALID_SCOPE");
        this.id=id;this.pkg=pkg;this.started=started;
    }
    static boolean validId(String id){return id!=null&&id.matches("[0-9a-f]{32}");}
    static boolean allowedPackage(String pkg){return "edu.sydney.transferlab".equals(pkg)||"edu.sydney.parameterroom".equals(pkg);}
    // Handler audit: WorkflowActivity.navigate; Back only when not dirty or pending.
    // This set conveys permission, not destination/route/hidden entity mapping.
    static boolean safeNavigation(String pkg,String rid){
        if(!"edu.sydney.transferlab".equals(pkg)||rid==null)return false;
        return rid.equals(pkg+":id/wfOpenLamp")||rid.equals(pkg+":id/wfOpenFan")
            ||rid.equals(pkg+":id/wfLampBack")||rid.equals(pkg+":id/wfFanBack");
    }
    void require(String scope,long now){
        if(!id.equals(scope))throw new IllegalStateException("SCOPE_MISMATCH");
        if(cancelled)throw new IllegalStateException("CANCELLED");
        if(now<started)throw new IllegalStateException("CLOCK_ERROR");
        if(now-started>=TOTAL_MS)throw new IllegalStateException("BUDGET_EXCEEDED");
    }
    void capture(String scope,long now){require(scope,now);if(captures>=MAX_CAPTURES)throw new IllegalStateException("BUDGET_EXCEEDED");captures++;}
    void observed(String obs,long now){observation=obs;observedAt=now;}
    void authorize(String scope,String obs,long now){
        require(scope,now);
        if(observation==null||!observation.equals(obs)||now<observedAt||now-observedAt>OBSERVATION_TTL_MS)
            throw new IllegalStateException("STALE_OBSERVATION");
        if(actions>=MAX_ACTIONS)throw new IllegalStateException("BUDGET_EXCEEDED");
        actions++;observation=null; // A permission is consumed even if dispatch later returns false.
    }
    void cancel(){cancelled=true;observation=null;}
}
