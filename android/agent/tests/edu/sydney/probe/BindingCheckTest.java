package edu.sydney.probe;

public final class BindingCheckTest {
    public static void main(String[] args) {
        SwitchSkill s = new SwitchSkill(ProbePolicy.TRANSFER_PACKAGE, ProbePolicy.TRANSFER_PACKAGE + ":id/mainToggle", false, true);
        eq("READY", BindingCheck.reason(s, new ReplayEngine.Scene(s.appPackage, 1, true, false)));
        eq("READY", BindingCheck.reason(s, new ReplayEngine.Scene(s.appPackage, 1, true, true)));
        eq("WRONG_APP", BindingCheck.reason(s, new ReplayEngine.Scene("other.app", 1, true, true)));
        eq("MISSING_TARGET", BindingCheck.reason(s, new ReplayEngine.Scene(s.appPackage, 0, true, true)));
        eq("AMBIGUOUS_TARGET", BindingCheck.reason(s, new ReplayEngine.Scene(s.appPackage, 2, true, true)));
        eq("UNUSABLE_TARGET", BindingCheck.reason(s, new ReplayEngine.Scene(s.appPackage, 1, false, true)));
        eq("NO_OBSERVATION", BindingCheck.reason(s, null));
        System.out.println("BindingCheckTest passed: 7 read-only applicability conditions");
    }
    private static void eq(String expected, String actual) {
        if (!expected.equals(actual)) throw new AssertionError(expected + " != " + actual);
    }
}
