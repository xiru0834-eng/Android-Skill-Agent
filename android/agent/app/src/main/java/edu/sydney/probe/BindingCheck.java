package edu.sydney.probe;

/** Applicability only; this check cannot authorize or produce an input action. */
public final class BindingCheck {
    private BindingCheck() {}
    public static String reason(SwitchSkill skill, ReplayEngine.Scene scene) {
        if (scene == null) return "NO_OBSERVATION";
        if (!skill.appPackage.equals(scene.appPackage)) return "WRONG_APP";
        if (scene.matches == 0) return "MISSING_TARGET";
        if (scene.matches != 1) return "AMBIGUOUS_TARGET";
        return scene.usable ? "READY" : "UNUSABLE_TARGET";
    }
}
