package edu.sydney.probe;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Immutable local approvals. Import only updates the draft, never the active deployment. */
public final class DeploymentStore {
    private static final String SESSION=java.util.UUID.randomUUID().toString();
    private final SharedPreferences prefs;
    public DeploymentStore(Context c) { this(c,"deployments"); }
    DeploymentStore(Context c,String name) { prefs=c.getSharedPreferences(name,0); }
    public DeploymentSkill draft() { return read("draft"); }
    public DeploymentSkill active() { return approved(prefs.getString("active","")); }
    private DeploymentSkill approved(String id) { DeploymentSkill s=read("approved."+id);return s!=null && s.bindingId.equals(id)?s:null; }
    public List<DeploymentSkill> history() {
        List<DeploymentSkill> result=new ArrayList<>();
        for(String key:prefs.getAll().keySet()) if(key.startsWith("approved.")) { DeploymentSkill s=approved(key.substring(9));if(s!=null) result.add(s); }
        result.sort(Comparator.comparing(s->s.bindingId));return result;
    }
    public boolean activate(String id) { return approved(id)!=null && prefs.edit().putString("active",id).commit(); }
    public boolean importDraft(String json) {
        DeploymentSkill s=DeploymentCodec.decode(json);validateHistory(s);
        return clear(prefs.edit()).putString("draft",DeploymentCodec.encode(s)).commit();
    }
    private void validateHistory(DeploymentSkill s) {
        String raw=prefs.getString("approved."+s.bindingId,null);
        if(raw!=null && !raw.equals(DeploymentCodec.encode(s))) throw new IllegalArgumentException("Approved version is immutable");
        for(DeploymentSkill old:history()) {
            if(old.workflowId.equals(s.workflowId) && (!old.roles.equals(s.roles) || !TwoStepCodec.encode(old.source).equals(TwoStepCodec.encode(s.source))))
                throw new IllegalArgumentException("Workflow identity conflict");
            if(old.bindingId.equals(s.parentBindingId) && !old.workflowId.equals(s.workflowId)) throw new IllegalArgumentException("Parent workflow conflict");
        }
    }
    public void checkResult(DeploymentSkill s,String reason) {
        DeploymentSkill current=draft();
        // An old callback must not revoke a newer draft's preflight result.
        if(current==null || !DeploymentCodec.encode(current).equals(DeploymentCodec.encode(s))) return;
        SharedPreferences.Editor e=clear(prefs.edit()).putString("reason",reason);
        if("READY".equals(reason)) e.putString("check",DeploymentCodec.encode(s)).putString("session",SESSION).putLong("checkAt",SystemClock.elapsedRealtime());
        e.commit();
    }
    public String reason() { return prefs.getString("reason","NOT_CHECKED"); }
    public boolean canReview() {
        DeploymentSkill s=draft();long at=prefs.getLong("checkAt",-1),now=SystemClock.elapsedRealtime();
        return s!=null && at>=0 && now>=at && now-at<=60000 && SESSION.equals(prefs.getString("session",""))
                && DeploymentCodec.encode(s).equals(prefs.getString("check",""));
    }
    public boolean review(String expected) {
        if(!canReview() || !DeploymentCodec.encode(draft()).equals(expected)) return false;
        DeploymentSkill s=draft();validateHistory(s);
        if(!prefs.contains("approved."+s.bindingId) && history().size()>=20) return false;
        return prefs.edit().putString("approved."+s.bindingId,expected).putString("active",s.bindingId).commit();
    }
    public void clearCheck() { clear(prefs.edit()).commit(); }
    private SharedPreferences.Editor clear(SharedPreferences.Editor e) { return e.remove("check").remove("checkAt").remove("session").remove("reason"); }
    private DeploymentSkill read(String key) { try { return DeploymentCodec.decode(prefs.getString(key,null)); } catch(IllegalArgumentException e) { return null; } }
}
