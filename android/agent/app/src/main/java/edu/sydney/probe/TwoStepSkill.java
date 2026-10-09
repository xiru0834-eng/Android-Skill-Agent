package edu.sydney.probe;

import java.util.List;

/** Two distinct boolean bindings; no coordinates, code or implicit approval. */
public final class TwoStepSkill {
    public final String appPackage;
    public final List<SwitchSkill> steps;
    public TwoStepSkill(List<SwitchSkill> steps) {
        if (steps == null || steps.size() != 2 || steps.get(0) == null || steps.get(1) == null
                || !steps.get(0).appPackage.equals(steps.get(1).appPackage)
                || steps.get(0).resourceId.equals(steps.get(1).resourceId))
            throw new IllegalArgumentException("Two distinct same-app targets required");
        this.steps = List.copyOf(steps); this.appPackage = steps.get(0).appPackage;
    }
}
