package edu.sydney.probe;

import java.util.List;
import java.util.regex.Pattern;

/** Strictly a review preview; no method here can execute or persist a step. */
public final class DraftSkill {
    public static final class Result {
        public final String code;
        public final String json;

        private Result(String code, String json) {
            this.code = code;
            this.json = json;
        }
    }

    private DraftSkill() {}

    public static Result compile(boolean recording, DemoTrace trace) {
        return compile(recording, trace, ProbePolicy.LAB_PACKAGE);
    }

    public static Result compile(boolean recording, DemoTrace trace, String appPackage) {
        if (recording) return rejected("RECORDING");
        List<DemoTrace.Step> steps = trace.steps();
        if (steps.isEmpty()) return rejected("NO_DEMONSTRATION");
        if (steps.size() != 1) return rejected("MULTI_STEP_UNSUPPORTED");
        if (trace.hasPending() || trace.unattributedChanges() != 0 || trace.unsupportedClicks() != 0)
            return rejected("INCOMPLETE_TRACE");
        DemoTrace.Step step = steps.get(0);
        if (!ProbePolicy.allowed(appPackage) || step.targetId == null
                || !step.targetId.matches(Pattern.quote(appPackage) + ":id/[A-Za-z0-9_]{1,80}"))
            return rejected("INVALID_TARGET");
        if (step.outcome != DemoTrace.Outcome.CHANGED || !isChecked(step.before)
                || !isChecked(step.after) || step.before.equals(step.after))
            return rejected("UNVERIFIED_STEP");
        String json = "{\"schemaVersion\":1,\"status\":\"DRAFT_NOT_EXECUTABLE\","
                + "\"appPackage\":\"" + appPackage + "\",\"workflow\":[{"
                + "\"operation\":\"TAP_NODE\",\"targetResourceId\":\"" + step.targetId + "\","
                + "\"precondition\":\"" + step.before + "\",\"expectedState\":\"" + step.after
                + "\"}]}";
        return new Result("READY_FOR_REVIEW", json);
    }

    private static boolean isChecked(String value) {
        return "checked=true".equals(value) || "checked=false".equals(value);
    }

    private static Result rejected(String code) { return new Result(code, ""); }
}
