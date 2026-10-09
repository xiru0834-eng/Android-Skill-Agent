package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import android.content.SharedPreferences;

/** Device tests for Android JSON and private storage; debug artifact only. */
public final class CodecChecks extends Instrumentation {
    private int invalidCount;
    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            SwitchSkill skill = new SwitchSkill(ProbePolicy.TRANSFER_PACKAGE, ProbePolicy.TRANSFER_PACKAGE + ":id/mainToggle", false, true);
            String json = SkillCodec.encode(skill);
            if (!SkillCodec.decode(json).resourceId.equals(skill.resourceId)) throw new AssertionError("roundtrip");
            reject(json.replace("\"schemaVersion\":1", "\"schemaVersion\":99"));
            reject(json.replace("SET_CHECKED", "EXEC_SHELL"));
            reject(json.replace("\"before\":false", "\"before\":\"false\""));
            reject(json.replace("\"binding\":", "\"extra\":true,\"binding\":"));
            reject(json.replace(ProbePolicy.TRANSFER_PACKAGE, "other.app"));
            reject(json + " trailing"); reject("{}"); reject("null");
            reject(json.replace("\"schemaVersion\":1", "\"schemaVersion\":99,\"schemaVersion\":1"));
            reject(json.replace("\"before\":false", "\"before\":true,\"before\":false"));
            reject(json.replace('"', '\''));
            reject("/* external comment */" + json);
            reject(json.replace("\"schemaVersion\":1", "\"schemaVersion\":1.0"));
            reject(json.replace("\"schemaVersion\":1", "\"schemaVersion\":\"1\""));
            reject(json.replace("\"before\":false", "\"before\":null"));
            reject(json.replace("\"before\":false", "\"before\":true"));
            reject(json.replace("\"binding\":", "\"approved\":true,\"binding\":"));
            reject(json.replace("\"resourceId\":", "\"coordinates\":[1,2],\"resourceId\":"));
            reject(json.replace("mainToggle", "../secret"));
            reject(json.substring(0, json.length() - 1));
            reject(" ".repeat(8193));
            reject(json.replace("\"workflow\":", "\"workflow\":{\"nested\":{},\"unused\":"));
            SharedPreferences prefs = getTargetContext().getSharedPreferences("codec_checks", 0);
            String key = "skill." + skill.appPackage;
            try {
                prefs.edit().clear().commit(); // Isolated test namespace; never user skills.
                SkillStore store = new SkillStore(getTargetContext(), "codec_checks");
                if (!store.importDraft(json) || store.load(skill.appPackage) != null || store.canReview(skill.appPackage))
                    throw new AssertionError("import approval separation");
                if (store.reviewDraft(skill.appPackage)) throw new AssertionError("approved without check");
                store.checkResult(skill, "MISSING_TARGET");
                if (store.canReview(skill.appPackage)) throw new AssertionError("failed check approved");
                store.checkResult(skill, "READY");
                if (!store.reviewDraft(skill.appPackage)) throw new AssertionError("checked review");
                String approved = prefs.getString(key, "");
                SwitchSkill changed = new SwitchSkill(skill.appPackage, skill.appPackage + ":id/otherToggle", false, true);
                store.importDraft(SkillCodec.encode(changed));
                if (store.canReview(skill.appPackage) || !approved.equals(prefs.getString(key, "")))
                    throw new AssertionError("replacement approval isolation");
                store.checkResult(skill, "READY");
                if (store.canReview(skill.appPackage)) throw new AssertionError("wrong candidate checked");
                String currentDraft = SkillCodec.encode(store.loadDraft(skill.appPackage));
                try { store.importDraft("{}"); throw new AssertionError("invalid import accepted"); }
                catch (IllegalArgumentException expected) { }
                if (!approved.equals(prefs.getString(key, "")) || !currentDraft.equals(SkillCodec.encode(store.loadDraft(skill.appPackage))))
                    throw new AssertionError("bad import changed stored data");
                store.checkResult(changed, "READY");
                prefs.edit().putLong("checkTime." + skill.appPackage, android.os.SystemClock.elapsedRealtime() - 60001).commit();
                if (store.canReview(skill.appPackage)) throw new AssertionError("expired check approved");
                store.checkResult(changed, "READY");
                prefs.edit().putString("checkSession." + skill.appPackage, "previous-process").commit();
                if (store.canReview(skill.appPackage)) throw new AssertionError("previous process check approved");
                store.checkResult(changed, "READY"); store.clearChecks();
                if (store.canReview(skill.appPackage)) throw new AssertionError("check survived reconnect");
                prefs.edit().remove(key).commit();
                store.draft(skill.appPackage, skill);
                if (store.load(skill.appPackage) != null || store.loadDraft(skill.appPackage) == null)
                    throw new AssertionError("draft approval separation");
                if (!store.saveReviewed(skill) || store.load(skill.appPackage) == null) throw new AssertionError("storage");
                prefs.edit().putString(key, "{}").commit();
                if (store.load(skill.appPackage) != null) throw new AssertionError("corrupt storage accepted");
            } finally {
                prefs.edit().clear().commit();
            }
            result.putString("result", "CodecChecks passed: roundtrip, " + invalidCount + " invalid payloads; import/approval isolation, expiry, reconnect, preservation, persistence, corrupt storage"); finish(-1, result);
        } catch (Throwable error) { result.putString("error", error.toString()); finish(1, result); }
    }
    private void reject(String json) {
        try { SkillCodec.decode(json); throw new AssertionError("invalid payload accepted"); }
        catch (IllegalArgumentException expected) { invalidCount++; }
    }
}
