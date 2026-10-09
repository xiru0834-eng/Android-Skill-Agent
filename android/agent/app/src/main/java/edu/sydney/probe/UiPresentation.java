package edu.sydney.probe;

import java.util.Locale;

/** Local display policy only. Never selects, approves or executes a skill. */
final class UiPresentation {
    private UiPresentation() {}
    static boolean matches(String name, String goal, String query) {
        String needle = query == null ? "" : query.strip().toLowerCase(Locale.ROOT);
        if (needle.isEmpty()) return true;
        return normal(name).contains(needle) || normal(goal).contains(needle);
    }
    private static String normal(String value) { return value == null ? "" : value.toLowerCase(Locale.ROOT); }
    static int stage(String kind) {
        if (kind == null) return 0;
        return switch (kind) {
            case "ENDED", "GENERATING", "REVIEW" -> 1;
            case "SAVED", "RUNNING" -> 2;
            default -> 0;
        };
    }
    static boolean stackActions(int widthDp, float fontScale) {
        // Pair decisions use the bounded page width, not a tablet's whole display.
        return contentWidthDp(widthDp)-40<344 || !Float.isFinite(fontScale) || fontScale>=1.25f;
    }
    static int contentWidthDp(int screenWidthDp) { return Math.max(0,Math.min(640,screenWidthDp)); }
    static String skillSteps(int count,boolean en) {
        if(count<=0)return en?"Open the guide":"查看操作指南";
        return en?count+(count==1?" recorded step":" recorded steps"):count+" 个记录步骤";
    }
    static int guideHeightDp(int screenHeightDp) { return Math.max(160,Math.min(360,Math.round(screenHeightDp*.35f))); }
}
