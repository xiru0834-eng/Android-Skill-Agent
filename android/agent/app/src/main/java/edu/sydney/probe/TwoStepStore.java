package edu.sydney.probe;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;

/** Independent namespace: v1 approvals and drafts are never migrated or overwritten. */
public final class TwoStepStore {
    private static final String SESSION=java.util.UUID.randomUUID().toString();
    private final SharedPreferences prefs;
    public TwoStepStore(Context context) { this(context,"two_step_skills"); }
    TwoStepStore(Context context,String name) { prefs=context.getSharedPreferences(name,0); }
    public TwoStepSkill load(String pkg) { return read("skill.",pkg); }
    public TwoStepSkill draft(String pkg) { return read("draft.",pkg); }
    public boolean setDraft(String pkg,TwoStepSkill skill,boolean imported) {
        if(!ProbePolicy.allowed(pkg) || (skill!=null && !pkg.equals(skill.appPackage))) throw new IllegalArgumentException("Package");
        SharedPreferences.Editor e=clearCheck(prefs.edit(),pkg).remove("origin."+pkg);
        if(skill==null) e.remove("draft."+pkg);
        else e.putString("draft."+pkg,TwoStepCodec.encode(skill)).putBoolean("origin."+pkg,imported);
        return e.commit();
    }
    public boolean importDraft(String json) {
        TwoStepSkill skill=TwoStepCodec.decode(json); return setDraft(skill.appPackage,skill,true);
    }
    public boolean imported(String pkg) { return prefs.getBoolean("origin."+pkg,false); }
    public void checkResult(TwoStepSkill skill,String reason) {
        String pkg=skill.appPackage; TwoStepSkill current=draft(pkg);
        SharedPreferences.Editor e=clearCheck(prefs.edit(),pkg).putString("reason."+pkg,reason);
        if("READY".equals(reason) && current!=null && TwoStepCodec.encode(current).equals(TwoStepCodec.encode(skill)))
            e.putString("check."+pkg,TwoStepCodec.encode(skill)).putString("session."+pkg,SESSION)
                    .putLong("time."+pkg,SystemClock.elapsedRealtime());
        e.commit();
    }
    public String checkReason(String pkg) { return prefs.getString("reason."+pkg,"NOT_CHECKED"); }
    public boolean canReview(String pkg) {
        TwoStepSkill skill=draft(pkg); if(skill==null) return false;
        if(!imported(pkg)) return true;
        long at=prefs.getLong("time."+pkg,-1),now=SystemClock.elapsedRealtime();
        return at>=0 && now>=at && now-at<=60000 && SESSION.equals(prefs.getString("session."+pkg,""))
                && TwoStepCodec.encode(skill).equals(prefs.getString("check."+pkg,""));
    }
    public boolean review(String pkg,String expected) {
        if(!canReview(pkg) || !TwoStepCodec.encode(draft(pkg)).equals(expected)) return false;
        return prefs.edit().putString("skill."+pkg,expected).commit();
    }
    public void clearChecks() {
        SharedPreferences.Editor e=prefs.edit();
        for(String pkg: new String[]{ProbePolicy.LAB_PACKAGE,ProbePolicy.TRANSFER_PACKAGE,ProbePolicy.ROOM_PACKAGE}) clearCheck(e,pkg);
        e.commit();
    }
    private SharedPreferences.Editor clearCheck(SharedPreferences.Editor e,String pkg) {
        return e.remove("check."+pkg).remove("session."+pkg).remove("time."+pkg).remove("reason."+pkg);
    }
    private TwoStepSkill read(String prefix,String pkg) {
        try { TwoStepSkill s=TwoStepCodec.decode(prefs.getString(prefix+pkg,null)); return s.appPackage.equals(pkg)?s:null; }
        catch(IllegalArgumentException e) { return null; }
    }
}
