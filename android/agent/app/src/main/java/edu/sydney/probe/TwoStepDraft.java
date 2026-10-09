package edu.sydney.probe;

import java.util.ArrayList;
import java.util.List;

public final class TwoStepDraft {
    private TwoStepDraft() { }
    public static String reason(boolean recording, DemoTrace trace, String pkg) {
        if (recording) return "RECORDING";
        if (trace.hasPending() || trace.unattributedChanges() != 0 || trace.unsupportedClicks() != 0)
            return "INCOMPLETE_TRACE";
        List<DemoTrace.Step> steps = trace.steps();
        if (steps.size() != 2) return "TWO_STEPS_REQUIRED";
        if (steps.get(0).targetId.equals(steps.get(1).targetId)) return "DISTINCT_TARGETS_REQUIRED";
        for (DemoTrace.Step step : steps) {
            if (step.outcome != DemoTrace.Outcome.CHANGED || !checked(step.before) || !checked(step.after))
                return "UNVERIFIED_STEP";
            try { new SwitchSkill(pkg, step.targetId, "checked=true".equals(step.before), "checked=true".equals(step.after)); }
            catch (IllegalArgumentException error) { return "INVALID_BINDING"; }
            if (!step.after.equals(trace.latestState().get(step.targetId))) return "FINAL_GOAL_MISMATCH";
        }
        return "READY_FOR_REVIEW";
    }
    public static TwoStepSkill compile(boolean recording, DemoTrace trace, String pkg) {
        if (!"READY_FOR_REVIEW".equals(reason(recording, trace, pkg))) return null;
        List<SwitchSkill> steps = new ArrayList<>();
        for (DemoTrace.Step step : trace.steps()) steps.add(new SwitchSkill(pkg, step.targetId,
                "checked=true".equals(step.before), "checked=true".equals(step.after)));
        return new TwoStepSkill(steps);
    }
    private static boolean checked(String s) { return "checked=true".equals(s) || "checked=false".equals(s); }
}
