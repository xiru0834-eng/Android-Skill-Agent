package edu.sydney.probe;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;

public final class SkillStore {
    private static final String CHECK_SESSION = java.util.UUID.randomUUID().toString();
    private final SharedPreferences prefs;
    public SkillStore(Context context) { this(context, "skills"); }
    SkillStore(Context context, String storeName) { prefs = context.getSharedPreferences(storeName, Context.MODE_PRIVATE); }
    public boolean saveReviewed(SwitchSkill skill) {
        String data = SkillCodec.encode(skill);
        SkillCodec.decode(data);
        return prefs.edit().putString("skill." + skill.appPackage, data).commit();
    }
    public SwitchSkill load(String pkg) {
        return read("skill.", pkg);
    }
    public SwitchSkill loadDraft(String pkg) { return read("draft.", pkg); }
    public void draft(String pkg, SwitchSkill skill) {
        SharedPreferences.Editor editor = prefs.edit().remove("origin." + pkg).remove("check." + pkg).remove("checkTime." + pkg)
                .remove("checkReason." + pkg).remove("checkSession." + pkg);
        if (skill == null) editor.remove("draft." + pkg).commit();
        else {
            if (!pkg.equals(skill.appPackage)) throw new IllegalArgumentException("Draft package mismatch");
            editor.putString("draft." + pkg, SkillCodec.encode(skill)).commit();
        }
    }
    public boolean importDraft(String json) {
        SwitchSkill skill = SkillCodec.decode(json); // Complete validation before any mutation.
        return prefs.edit().putString("draft." + skill.appPackage, SkillCodec.encode(skill))
                .putString("origin." + skill.appPackage, "IMPORTED")
                .remove("check." + skill.appPackage).remove("checkTime." + skill.appPackage)
                .remove("checkReason." + skill.appPackage).remove("checkSession." + skill.appPackage).commit();
    }
    public boolean imported(String pkg) { return "IMPORTED".equals(prefs.getString("origin." + pkg, "")); }
    public void checkResult(SwitchSkill skill, String reason) {
        SharedPreferences.Editor editor = prefs.edit().putString("checkReason." + skill.appPackage, reason)
                .remove("check." + skill.appPackage).remove("checkTime." + skill.appPackage).remove("checkSession." + skill.appPackage);
        SwitchSkill current = loadDraft(skill.appPackage);
        if ("READY".equals(reason) && current != null && SkillCodec.encode(current).equals(SkillCodec.encode(skill)))
            editor.putString("check." + skill.appPackage, SkillCodec.encode(skill))
                    .putString("checkSession." + skill.appPackage, CHECK_SESSION)
                    .putLong("checkTime." + skill.appPackage, SystemClock.elapsedRealtime());
        editor.commit();
    }
    public String checkReason(String pkg) { return prefs.getString("checkReason." + pkg, "NOT_CHECKED"); }
    public void clearChecks() {
        SharedPreferences.Editor editor = prefs.edit();
        for (String key : prefs.getAll().keySet())
            if (key.startsWith("check.") || key.startsWith("checkTime.") || key.startsWith("checkReason.")
                    || key.startsWith("checkSession.")) editor.remove(key);
        editor.commit();
    }
    public boolean canReview(String pkg) {
        SwitchSkill skill = loadDraft(pkg);
        if (skill == null) return false;
        if (!imported(pkg)) return true;
        long checkedAt = prefs.getLong("checkTime." + pkg, -1), now = SystemClock.elapsedRealtime();
        return checkedAt >= 0 && now >= checkedAt && now - checkedAt <= 60000
                && CHECK_SESSION.equals(prefs.getString("checkSession." + pkg, ""))
                && SkillCodec.encode(skill).equals(prefs.getString("check." + pkg, ""));
    }
    public boolean reviewDraft(String pkg) {
        if (!canReview(pkg)) return false;
        return saveReviewed(loadDraft(pkg));
    }
    private SwitchSkill read(String prefix, String pkg) {
        try {
            SwitchSkill skill = SkillCodec.decode(prefs.getString(prefix + pkg, null));
            return skill.appPackage.equals(pkg) ? skill : null;
        } catch (IllegalArgumentException e) { return null; }
    }
    public void result(String json) { prefs.edit().putString("last_result", json).commit(); }
    public String result() { return prefs.getString("last_result", "No execution yet"); }
}
