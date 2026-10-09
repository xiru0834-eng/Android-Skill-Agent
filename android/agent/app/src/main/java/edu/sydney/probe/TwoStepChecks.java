package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import android.content.SharedPreferences;
import java.util.List;

public final class TwoStepChecks extends Instrumentation {
    private int invalid;
    @Override public void onCreate(Bundle args) { super.onCreate(args);start(); }
    @Override public void onStart() {
        Bundle out=new Bundle();
        try {
            String pkg=ProbePolicy.TRANSFER_PACKAGE;
            TwoStepSkill s=new TwoStepSkill(List.of(new SwitchSkill(pkg,pkg+":id/mainToggle",false,true),new SwitchSkill(pkg,pkg+":id/otherToggle",false,true)));
            String json=TwoStepCodec.encode(s);
            check(json.equals(TwoStepCodec.encode(TwoStepCodec.decode(json))),"roundtrip");
            for(String bad:List.of("{}","null",json+" x",json.replace("\"schemaVersion\":2","\"schemaVersion\":1"),
                    json.replace("\"schemaVersion\":2","\"schemaVersion\":2.0"),json.replace("\"schemaVersion\":2","\"schemaVersion\":\"2\""),
                    json.replace("\"schemaVersion\":2","\"schemaVersion\":2,\"schemaVersion\":2"),json.replace("SET_TWO_CHECKED","SHELL"),
                    json.replace("\"before\":false","\"before\":\"false\""),json.replace("\"before\":false","\"before\":null"),
                    json.replace("\"before\":false","\"before\":true"),json.replace("\"before\":false","\"before\":true,\"before\":false"),
                    json.replace("otherToggle","mainToggle"),json.replace(pkg,"other.app"),json.replace("mainToggle","../secret"),
                    json.replace("\"steps\":","\"approved\":true,\"steps\":"),json.replace("\"before\":false","\"coords\":[1,2],\"before\":false"),
                    json.replace('"','\''),"/* comment */"+json,json.substring(0,json.length()-1)," ".repeat(8193),
                    json.replace("\"steps\":[","\"steps\":[{},"))) reject(bad);
            org.json.JSONObject root=new org.json.JSONObject(json);
            org.json.JSONArray a=root.getJSONArray("steps"); a.put(a.get(0));reject(root.toString());
            a.remove(2);a.remove(1);reject(root.toString());
            try { SkillCodec.decode(json);throw new AssertionError("v2 accepted by v1"); } catch(IllegalArgumentException expected) { }
            reject(SkillCodec.encode(s.steps.get(0)));
            SharedPreferences p=getTargetContext().getSharedPreferences("two_step_checks",0);
            try {
                p.edit().clear().commit();TwoStepStore store=new TwoStepStore(getTargetContext(),"two_step_checks");
                check(store.importDraft(json),"import");check(store.load(pkg)==null && !store.canReview(pkg),"import not approval");
                check(!store.review(pkg,json),"review without check");store.checkResult(s,"MISSING_TARGET");check(!store.canReview(pkg),"negative check");
                store.checkResult(s,"READY");check(store.review(pkg,json),"review");
                TwoStepSkill changed=new TwoStepSkill(List.of(s.steps.get(1),s.steps.get(0)));String changedJson=TwoStepCodec.encode(changed);
                store.importDraft(changedJson);check(!store.canReview(pkg) && json.equals(TwoStepCodec.encode(store.load(pkg))),"preserve old approval");
                store.checkResult(s,"READY");check(!store.canReview(pkg),"wrong candidate");
                try { store.importDraft("{}");throw new AssertionError("invalid import"); }catch(IllegalArgumentException expected) { }
                check(changedJson.equals(TwoStepCodec.encode(store.draft(pkg))) && json.equals(TwoStepCodec.encode(store.load(pkg))),"invalid preserved");
                store.checkResult(changed,"READY");check(!store.review(pkg,json),"stale dialog");
                p.edit().putLong("time."+pkg,android.os.SystemClock.elapsedRealtime()-60001).commit();check(!store.canReview(pkg),"expired");
                store.checkResult(changed,"READY");p.edit().putString("session."+pkg,"old-process").commit();check(!store.canReview(pkg),"process token");
                store.checkResult(changed,"READY");store.clearChecks();check(!store.canReview(pkg),"service token");
                store.setDraft(pkg,s,false);check(store.canReview(pkg) && store.review(pkg,json),"local review");
                p.edit().putString("skill."+pkg,"{}").commit();check(store.load(pkg)==null,"corrupt storage");
            } finally { p.edit().clear().commit(); }
            out.putString("result","TwoStepChecks passed: "+invalid+" rejected payloads, roundtrip, approval separation, preservation, tokens, stale review, corrupt storage");finish(-1,out);
        } catch(Throwable e) { out.putString("error",e.toString());finish(1,out); }
    }
    private void reject(String json) { try { TwoStepCodec.decode(json);throw new AssertionError("accepted malformed payload"); }catch(IllegalArgumentException expected) { invalid++; } }
    private void check(boolean ok,String message) { if(!ok) throw new AssertionError(message); }
}
