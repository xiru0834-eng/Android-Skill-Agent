package edu.sydney.probe;

import java.util.List;

/** observe returns a click index (0/1), -1 WAIT, or -2 DONE. One total deadline. */
public final class TwoStepEngine {
    public final TwoStepSkill skill;
    public final List<Boolean> desired;
    public final long startedAt, deadline;
    public String status = "RUNNING", reason = "WAITING_FOR_APP";
    public int inputs, observations, completed;
    public long finishedAt;
    private final boolean[] issued = new boolean[2];
    private long targetSince = -1, jointSince = -1;
    public TwoStepEngine(TwoStepSkill skill, List<Boolean> desired, long start, long budget) {
        if (skill == null || desired == null || desired.size() != 2 || desired.get(0) == null || desired.get(1) == null
                || start < 0 || budget <= 0 || budget > 10000 || start > Long.MAX_VALUE-budget)
            throw new IllegalArgumentException("Invalid run");
        this.skill = skill; this.desired = List.copyOf(desired); startedAt = start; deadline = start + budget;
    }
    public static String bindingReason(TwoStepSkill skill, List<ReplayEngine.Scene> scenes) {
        if (scenes == null || scenes.size() != 2) return "NO_OBSERVATION";
        for (int i=0;i<2;i++) {
            String reason = BindingCheck.reason(skill.steps.get(i), scenes.get(i));
            if (!"READY".equals(reason)) return reason;
        }
        return "READY";
    }
    public int observe(List<ReplayEngine.Scene> scenes, long now) {
        if (!running()) return -2;
        if (now >= deadline) return finish("UNCONFIRMED", "DEADLINE", now);
        observations++;
        String gate = bindingReason(skill, scenes);
        if (!"READY".equals(gate)) return finish(inputs == 0 ? "REFUSED" : "UNCONFIRMED", gate, now);
        // Previously verified steps remain obligations, not historical success flags.
        for (int i=0;i<completed;i++) if (scenes.get(i).checked != desired.get(i))
            return finish("UNCONFIRMED", "GOAL_REGRESSED", now);
        if (completed == 2) {
            if (now-jointSince >= 150) return finish("SUCCEEDED", inputs==0 ? "ALREADY_AT_TARGETS" : "JOINT_TARGETS_VERIFIED", now);
            return -1;
        }
        if (scenes.get(completed).checked == desired.get(completed)) {
            if (targetSince < 0) targetSince = now;
            if (now-targetSince >= 150) {
                completed++; targetSince = -1;
                if (completed == 2) jointSince = now;
            }
            reason = "VERIFYING"; return -1;
        }
        targetSince = -1;
        if (!issued[completed]) {
            issued[completed] = true; inputs++; reason = "INPUT_PLANNED"; return completed;
        }
        reason = "WAITING_FOR_TARGET"; return -1;
    }
    public boolean running() { return "RUNNING".equals(status); }
    public void cancel(long now) { if (running()) finish("CANCELLED","USER_STOP",now); }
    public void inputRejected(long now) { if (running()) finish("UNCONFIRMED","INPUT_REJECTED",now); }
    public void observationFailed(long now) { if (running()) finish("UNCONFIRMED","OBSERVATION_ERROR",now); }
    private int finish(String status,String reason,long now) { this.status=status;this.reason=reason;finishedAt=now;return -2; }
}
