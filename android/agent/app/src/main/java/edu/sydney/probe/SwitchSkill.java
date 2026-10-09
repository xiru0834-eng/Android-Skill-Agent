package edu.sydney.probe;

import java.util.regex.Pattern;

/** The workflow is common; only the deployment binding varies across apps. */
public final class SwitchSkill {
    public final String appPackage;
    public final String resourceId;
    public final boolean demonstratedBefore;
    public final boolean defaultDesired;

    public SwitchSkill(String appPackage, String resourceId, boolean before, boolean after) {
        if (!ProbePolicy.allowed(appPackage) || resourceId == null
                || !resourceId.matches(Pattern.quote(appPackage) + ":id/[A-Za-z0-9_]{1,80}")
                || before == after) throw new IllegalArgumentException("Invalid switch binding/evidence");
        this.appPackage = appPackage;
        this.resourceId = resourceId;
        this.demonstratedBefore = before;
        this.defaultDesired = after;
    }
}
