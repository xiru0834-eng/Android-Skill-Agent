package edu.sydney.probe;

public final class ReplayEngineTest {
    private static final String PKG = "edu.sydney.transferlab";
    private static final String ID = PKG + ":id/mainToggle";
    private static ReplayEngine engine(boolean desired) {
        return new ReplayEngine(new SwitchSkill(PKG, ID, false, true), desired, 0, 3500);
    }
    private static ReplayEngine.Scene scene(String pkg, int count, boolean usable, boolean checked) {
        return new ReplayEngine.Scene(pkg, count, usable, checked);
    }
    public static void main(String[] args) {
        ReplayEngine e = engine(true);
        eq(ReplayEngine.Action.CLICK, e.observe(scene(PKG, 1, true, false), 800));
        eq(ReplayEngine.Action.WAIT, e.observe(scene(PKG, 1, true, false), 1000));
        eq(ReplayEngine.Action.WAIT, e.observe(scene(PKG, 1, true, true), 1200));
        eq(ReplayEngine.Action.DONE, e.observe(scene(PKG, 1, true, true), 1400));
        eq("SUCCEEDED", e.status); eq(1, e.inputs);
        eq(ReplayEngine.Action.DONE, e.observe(scene(PKG, 1, true, false), 1500));

        e = engine(true);
        e.observe(scene(PKG, 1, true, true), 800);
        e.observe(scene(PKG, 1, true, true), 850);
        eq("RUNNING", e.status);
        e.observe(scene(PKG, 1, true, true), 1000);
        eq("ALREADY_AT_TARGET", e.reason); eq(0, e.inputs);

        e = engine(false);
        eq(ReplayEngine.Action.CLICK, e.observe(scene(PKG, 1, true, true), 800));
        e.observe(scene(PKG, 1, true, false), 1000);
        e.observe(scene(PKG, 1, true, false), 1200);
        eq("SUCCEEDED", e.status);

        for (int count : new int[]{0, 2}) {
            e = engine(true); e.observe(scene(PKG, count, true, false), 800);
            eq("REFUSED", e.status); eq(0, e.inputs);
        }
        e = engine(true); e.observe(scene("other.app", 1, true, false), 800);
        eq("WRONG_APP", e.reason); eq(0, e.inputs);
        e = engine(true); e.observe(scene(PKG, 1, false, false), 800);
        eq("UNUSABLE_TARGET", e.reason); eq(0, e.inputs);

        e = engine(true); e.observe(scene(PKG, 1, true, false), 800);
        e.observe(scene(PKG, 1, true, false), 3500);
        eq("UNCONFIRMED", e.status); eq(1, e.inputs);
        e = engine(true); e.observe(scene(PKG, 1, true, false), 3500);
        eq(0, e.inputs); eq("DEADLINE", e.reason);
        e = engine(true); e.cancel(100); e.observe(scene(PKG, 1, true, false), 800);
        eq("CANCELLED", e.status); eq(0, e.inputs);
        e = engine(true); e.observe(scene(PKG, 1, true, false), 800); e.inputRejected(810);
        eq("UNCONFIRMED", e.status); eq("INPUT_REJECTED", e.reason);
        e = engine(true); e.observe(scene(PKG, 1, true, false), 800);
        e.observe(scene(PKG, 1, true, true), 1000);
        e.observe(scene(PKG, 1, true, false), 1100);
        e.observe(scene(PKG, 1, true, true), 1200);
        eq("RUNNING", e.status);

        badSkill("other.app", "other.app:id/a", false, true);
        badSkill(PKG, "edu.sydney.smarthomelab:id/lightSwitch", false, true);
        badSkill(PKG, PKG + ":id/a\"", false, true);
        badSkill(PKG, ID, true, true);
        System.out.println("ReplayEngineTest passed");
    }
    private static void badSkill(String pkg, String id, boolean before, boolean after) {
        try { new SwitchSkill(pkg, id, before, after); throw new AssertionError("accepted invalid skill"); }
        catch (IllegalArgumentException expected) { }
    }
    private static void eq(Object expected, Object actual) {
        if (!expected.equals(actual)) throw new AssertionError(expected + " != " + actual);
    }
}
