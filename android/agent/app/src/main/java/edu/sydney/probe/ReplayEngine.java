package edu.sydney.probe;

/** One input maximum. A boolean parameter controls the desired observable state. */
public final class ReplayEngine {
    public enum Action { CLICK, WAIT, DONE }
    public static final class Scene {
        public final String appPackage;
        public final int matches;
        public final boolean usable;
        public final boolean checked;
        public Scene(String appPackage, int matches, boolean usable, boolean checked) {
            this.appPackage = appPackage; this.matches = matches;
            this.usable = usable; this.checked = checked;
        }
    }
    public final SwitchSkill skill;
    public final boolean desired;
    public final long startedAt;
    public final long deadline;
    public String status = "RUNNING";
    public String reason = "WAITING_FOR_APP";
    public int inputs;
    public int observations;
    public long finishedAt;
    public Boolean initialObserved;
    private long targetSince = -1;

    public ReplayEngine(SwitchSkill skill, boolean desired, long startedAt, long budgetMs) {
        if (skill == null || startedAt < 0 || budgetMs <= 0 || budgetMs > 10000)
            throw new IllegalArgumentException("Invalid run");
        this.skill = skill; this.desired = desired; this.startedAt = startedAt;
        this.deadline = startedAt + budgetMs;
    }
    public Action observe(Scene scene, long now) {
        if (!"RUNNING".equals(status)) return Action.DONE;
        if (now >= deadline) return finish("UNCONFIRMED", "DEADLINE", now);
        observations++;
        if (scene == null || !skill.appPackage.equals(scene.appPackage))
            return finish(inputs == 0 ? "REFUSED" : "UNCONFIRMED", "WRONG_APP", now);
        if (scene.matches != 1)
            return finish(inputs == 0 ? "REFUSED" : "UNCONFIRMED",
                    scene.matches == 0 ? "MISSING_TARGET" : "AMBIGUOUS_TARGET", now);
        if (!scene.usable)
            return finish(inputs == 0 ? "REFUSED" : "UNCONFIRMED", "UNUSABLE_TARGET", now);
        if (initialObserved == null) initialObserved = scene.checked;
        if (scene.checked == desired) {
            if (targetSince < 0) targetSince = now;
            else if (now - targetSince >= 150)
                return finish("SUCCEEDED", inputs == 0 ? "ALREADY_AT_TARGET" : "TARGET_VERIFIED", now);
            return Action.WAIT;
        }
        targetSince = -1;
        if (inputs == 0) {
            inputs = 1;
            reason = "VERIFYING";
            return Action.CLICK;
        }
        return Action.WAIT;
    }
    public void inputRejected(long now) { finish("UNCONFIRMED", "INPUT_REJECTED", now); }
    public void observationFailed(long now) { finish("UNCONFIRMED", "OBSERVATION_ERROR", now); }
    public void cancel(long now) { finish("CANCELLED", "USER_STOP", now); }
    private Action finish(String status, String reason, long now) {
        if ("RUNNING".equals(this.status)) {
            this.status = status; this.reason = reason; this.finishedAt = now;
        }
        return Action.DONE;
    }
}
