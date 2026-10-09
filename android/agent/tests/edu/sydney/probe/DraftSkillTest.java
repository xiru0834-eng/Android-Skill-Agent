package edu.sydney.probe;

import java.util.Map;

public final class DraftSkillTest {
    private static final String LIGHT = "edu.sydney.smarthomelab:id/lightSwitch";

    public static void main(String[] args) {
        DemoTrace valid = new DemoTrace();
        valid.setBaseline(Map.of(LIGHT, "checked=false"));
        valid.onClick(LIGHT, 1);
        valid.completeClick(Map.of(LIGHT, "checked=true"));
        DraftSkill.Result ready = DraftSkill.compile(false, valid);
        check("READY_FOR_REVIEW".equals(ready.code), "valid switch accepted");
        check(ready.json.contains("\"status\":\"DRAFT_NOT_EXECUTABLE\""), "draft status");
        check(ready.json.contains("\"targetResourceId\":\"" + LIGHT + "\""), "target id");
        check(ready.json.contains("\"precondition\":\"checked=false\""), "before");
        check(ready.json.contains("\"expectedState\":\"checked=true\""), "after");
        check(ready.json.contains("\"schemaVersion\":1"), "version");
        check("RECORDING".equals(DraftSkill.compile(true, valid).code), "do not draft while recording");
        check("NO_DEMONSTRATION".equals(DraftSkill.compile(false, new DemoTrace()).code), "empty trace");

        valid.onClick(LIGHT, 2);
        valid.completeClick(Map.of(LIGHT, "checked=false"));
        check("MULTI_STEP_UNSUPPORTED".equals(DraftSkill.compile(false, valid).code), "two steps rejected");

        DemoTrace orphan = new DemoTrace();
        orphan.setBaseline(Map.of(LIGHT, "checked=false"));
        orphan.observeUnattributed(Map.of(LIGHT, "checked=true"));
        orphan.onClick(LIGHT, 3);
        orphan.completeClick(Map.of(LIGHT, "checked=false"));
        check("INCOMPLETE_TRACE".equals(DraftSkill.compile(false, orphan).code), "orphan rejected");

        DemoTrace missing = new DemoTrace();
        missing.onClick(null, 4);
        missing.setBaseline(Map.of(LIGHT, "checked=false"));
        missing.onClick(LIGHT, 5);
        missing.completeClick(Map.of(LIGHT, "checked=true"));
        check("INCOMPLETE_TRACE".equals(DraftSkill.compile(false, missing).code), "missing id rejected");

        DemoTrace unobservable = new DemoTrace();
        unobservable.setBaseline(Map.of());
        unobservable.onClick("edu.sydney.smarthomelab:id/airconPlus", 6);
        unobservable.completeClick(Map.of());
        check("UNVERIFIED_STEP".equals(DraftSkill.compile(false, unobservable).code), "aircon not asserted");

        DemoTrace unchanged = new DemoTrace();
        unchanged.setBaseline(Map.of(LIGHT, "checked=false"));
        unchanged.onClick(LIGHT, 7);
        unchanged.completeClick(Map.of(LIGHT, "checked=false"));
        check("UNVERIFIED_STEP".equals(DraftSkill.compile(false, unchanged).code), "unchanged rejected");

        DemoTrace rapid = new DemoTrace();
        rapid.setBaseline(Map.of(LIGHT, "checked=false"));
        rapid.onClick(LIGHT, 8);
        rapid.abandonPending();
        check("UNVERIFIED_STEP".equals(DraftSkill.compile(false, rapid).code), "rapid rejected");

        DemoTrace foreign = new DemoTrace();
        String badId = "other.app:id/\"oops";
        foreign.setBaseline(Map.of(badId, "checked=false"));
        foreign.onClick(badId, 9);
        foreign.completeClick(Map.of(badId, "checked=true"));
        check("INVALID_TARGET".equals(DraftSkill.compile(false, foreign).code), "foreign id rejected");
        DemoTrace other = new DemoTrace();
        String secondId = ProbePolicy.TRANSFER_PACKAGE + ":id/mainToggle";
        other.setBaseline(Map.of(secondId, "checked=false"));
        other.onClick(secondId, 10);
        other.completeClick(Map.of(secondId, "checked=true"));
        check("READY_FOR_REVIEW".equals(DraftSkill.compile(false, other, ProbePolicy.TRANSFER_PACKAGE).code), "second app accepted explicitly");
        check("INVALID_TARGET".equals(DraftSkill.compile(false, other).code), "cross-app recording not merged");
        System.out.println("DraftSkillTest passed");
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
