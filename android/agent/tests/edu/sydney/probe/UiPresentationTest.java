package edu.sydney.probe;

public final class UiPresentationTest {
    private static int checks;
    public static void main(String[] args) {
        check(UiPresentation.matches("阅读60 / Reading60", "Turn on the lamp", "reading60"));
        check(UiPresentation.matches("阅读60 / Reading60", "Turn on the lamp", "阅读"));
        check(UiPresentation.matches("Fan low", "Turn on the fan", " FAN "));
        check(UiPresentation.matches("Lamp", "Set brightness to 60%", "60%"));
        check(UiPresentation.matches("Lamp", "Set brightness", "  "));
        check(!UiPresentation.matches("Lamp", "Set brightness", "curtain"));
        check(!UiPresentation.matches(null, null, "lamp"));
        check(UiPresentation.matches(null, null, null));
        check(UiPresentation.stage("RECORDING") == 0);
        check(UiPresentation.stage("CONFIRMING") == 0);
        check(UiPresentation.stage("ENDED") == 1);
        check(UiPresentation.stage("GENERATING") == 1);
        check(UiPresentation.stage("REVIEW") == 1);
        check(UiPresentation.stage("SAVED") == 2);
        check(UiPresentation.stage("RUNNING") == 2);
        check(UiPresentation.stage("FUTURE_STATE") == 0);
        check(UiPresentation.stage(null) == 0);
        check(UiPresentation.stackActions(320, 1f));
        check(!UiPresentation.stackActions(384, 1f));
        check(UiPresentation.stackActions(640, 1.3f));
        check(UiPresentation.stackActions(0, 1f));
        check(UiPresentation.stackActions(384, Float.NaN));
        check(UiPresentation.contentWidthDp(320) == 320);
        check(UiPresentation.contentWidthDp(1000) == 640);
        check(UiPresentation.contentWidthDp(0) == 0);
        check(UiPresentation.stackActions(360, 1f));
        check(UiPresentation.stackActions(1000, 1.25f));
        check(!UiPresentation.stackActions(1000, 1f));
        check(UiPresentation.skillSteps(1, true).equals("1 recorded step"));
        check(UiPresentation.skillSteps(8, true).equals("8 recorded steps"));
        check(UiPresentation.skillSteps(8, false).equals("8 个记录步骤"));
        check(UiPresentation.skillSteps(0, false).equals("查看操作指南"));
        check(UiPresentation.skillSteps(-1, true).equals("Open the guide"));
        check(UiPresentation.guideHeightDp(320) == 160);
        check(UiPresentation.guideHeightDp(800) == 280);
        check(UiPresentation.guideHeightDp(2000) == 360);
        System.out.println("UiPresentationTest: " + checks + " checks passed");
    }
    private static void check(boolean value) { checks++; if (!value) throw new AssertionError("check " + checks); }
}
