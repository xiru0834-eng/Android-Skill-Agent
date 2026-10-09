package edu.sydney.probe;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

/** Local evidence, never an approval. No pixels or arbitrary screen text are stored. */
public final class TraceBundle {
    public enum Source { UNKNOWN, HUMAN_DECLARED, ADB_TEST }
    public enum End { RECORDING, STOPPED, TIMED_OUT, INTERRUPTED }
    public static final class Step {
        public final String targetId, before, after;
        public final long eventTime;
        public final DemoTrace.Outcome outcome;
        public Step(String id,long time,String before,String after,DemoTrace.Outcome outcome) {
            if(time<0 || outcome==null) throw new IllegalArgumentException("Step metadata");
            targetId=id;eventTime=time;this.before=before;this.after=after;this.outcome=outcome;
        }
    }
    public final String traceId, appPackage, appVersion, goal;
    public final Source source;
    public final End end;
    public final List<Step> steps;
    public final Map<String,String> finalState;
    public final int unattributedChanges, unsupportedClicks, overflowClicks;

    public TraceBundle(String id,String pkg,String version,String goal,Source source,End end,
            List<Step> steps,Map<String,String> finalState,int unmatched,int unsupported,int overflow) {
        if(id==null || !UUID.fromString(id).toString().equals(id) || !ProbePolicy.allowed(pkg)
                || !safeText(version,80) || !safeText(goal,240) || source==null || end==null
                || steps==null || steps.size()>30 || finalState==null || finalState.size()>100
                || unmatched<0 || unsupported<0 || overflow<0) throw new IllegalArgumentException("Trace metadata");
        long last=-1;
        for(Step step:steps) {
            if(step==null || !validId(pkg,step.targetId) || step.eventTime<last
                    || !validState(step.before) || !validState(step.after)) throw new IllegalArgumentException("Step evidence");
            last=step.eventTime;
            boolean missing=step.before==null || step.after==null;
            if(step.outcome==DemoTrace.Outcome.CHANGED && (missing || step.before.equals(step.after))
                    || step.outcome==DemoTrace.Outcome.UNCHANGED && (missing || !step.before.equals(step.after))
                    || step.outcome==DemoTrace.Outcome.UNOBSERVABLE && !missing
                    || step.outcome==DemoTrace.Outcome.RAPID_UNCONFIRMED && step.after!=null)
                throw new IllegalArgumentException("Outcome contradicts evidence");
        }
        for(Map.Entry<String,String> field:finalState.entrySet())
            if(!validId(pkg,field.getKey()) || field.getValue()==null || !validState(field.getValue()))
                throw new IllegalArgumentException("Final evidence");
        traceId=id;appPackage=pkg;appVersion=version;this.goal=goal;this.source=source;this.end=end;
        this.steps=List.copyOf(steps);this.finalState=Map.copyOf(finalState);
        unattributedChanges=unmatched;unsupportedClicks=unsupported;overflowClicks=overflow;
    }
    public static TraceBundle capture(String id,String pkg,String version,String goal,Source source,End end,DemoTrace trace) {
        List<Step> steps=new ArrayList<>();
        for(DemoTrace.Step step:trace.steps()) steps.add(new Step(step.targetId,step.eventTime,step.before,step.after,step.outcome));
        // Pending input cannot become a valid stopped record through a serialization boundary.
        End actual=trace.hasPending() && end==End.STOPPED?End.INTERRUPTED:end;
        return new TraceBundle(id,pkg,version,goal,source,actual,steps,trace.latestState(),
                trace.unattributedChanges(),trace.unsupportedClicks(),trace.overflowClicks());
    }
    public String candidateReason() {
        if(end!=End.STOPPED) return "RECORDING_NOT_STOPPED";
        if(goal.isBlank()) return "TASK_GOAL_REQUIRED";
        if(unattributedChanges!=0 || unsupportedClicks!=0 || overflowClicks!=0) return "INCOMPLETE_TRACE";
        if(steps.size()!=2) return "TWO_STEPS_REQUIRED";
        if(steps.get(0).targetId.equals(steps.get(1).targetId)) return "DISTINCT_TARGETS_REQUIRED";
        for(Step step:steps) {
            if(step.outcome!=DemoTrace.Outcome.CHANGED || !checked(step.before) || !checked(step.after)) return "UNVERIFIED_STEP";
            if(!step.after.equals(finalState.get(step.targetId))) return "FINAL_GOAL_MISMATCH";
        }
        return "READY_FOR_REVIEW";
    }
    public TwoStepSkill candidate() {
        if(!"READY_FOR_REVIEW".equals(candidateReason())) return null;
        List<SwitchSkill> result=new ArrayList<>();
        for(Step step:steps) result.add(new SwitchSkill(appPackage,step.targetId,"checked=true".equals(step.before),"checked=true".equals(step.after)));
        return new TwoStepSkill(result);
    }
    private static boolean validId(String pkg,String id) {
        return id!=null && id.matches(Pattern.quote(pkg)+":id/[A-Za-z0-9_]{1,80}");
    }
    private static boolean checked(String state) { return "checked=true".equals(state) || "checked=false".equals(state); }
    private static boolean validState(String state) {
        if(state==null || checked(state)) return true;
        if(!state.startsWith("range=") || state.length()>40) return false;
        try { return Double.isFinite(Double.parseDouble(state.substring(6))); }
        catch(NumberFormatException error) { return false; }
    }
    private static boolean safeText(String value,int max) {
        if(value==null || value.length()>max) return false;
        for(int i=0;i<value.length();i++) if(Character.isISOControl(value.charAt(i))) return false;
        return true;
    }
}
