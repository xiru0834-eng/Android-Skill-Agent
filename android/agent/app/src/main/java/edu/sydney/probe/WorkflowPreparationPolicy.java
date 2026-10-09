package edu.sydney.probe;

/** Entry-only gate; readiness is consistency, not proof of observation freshness. */
final class WorkflowPreparationPolicy {
    private final long deadline;
    private final String expectedPage;
    private boolean cancelled;
    private String previous;
    private long firstSeen;
    WorkflowPreparationPolicy(long started,String expectedPage){
        if(started<0||!(expectedPage.isEmpty()||expectedPage.equals("single")||expectedPage.equals("overview")))throw new IllegalArgumentException("PREPARATION_CONFIG");
        deadline=started+60000;this.expectedPage=expectedPage;
    }
    String observe(long now,String page,boolean dirty,String snapshot){
        if(cancelled)return "CANCELLED";
        if(now>=deadline){previous=null;return "TIMED_OUT";}
        String decision;
        if(page==null||snapshot==null||!java.util.List.of("single","overview","lamp","fan").contains(page))decision="WAIT";
        else if(dirty)decision="UNSAVED";
        else if(page.equals("lamp")||page.equals("fan"))decision="RETURN_OVERVIEW";
        else if(!expectedPage.isEmpty()&&!expectedPage.equals(page))decision=expectedPage.equals("single")?"SWITCH_SINGLE":"SWITCH_PAGES";
        else {
            if(!snapshot.equals(previous)){previous=snapshot;firstSeen=now;return "STABILIZING";}
            return now-firstSeen>=250?"READY":"STABILIZING";
        }
        previous=null;return decision;
    }
    boolean mayStart(long now,String page,boolean dirty,String snapshot){
        return !cancelled&&now<deadline&&!dirty&&page!=null&&snapshot!=null&&snapshot.equals(previous)&&now-firstSeen>=250
            &&(page.equals("single")||page.equals("overview"))&&(expectedPage.isEmpty()||expectedPage.equals(page));
    }
    void cancel(){cancelled=true;previous=null;}
}
