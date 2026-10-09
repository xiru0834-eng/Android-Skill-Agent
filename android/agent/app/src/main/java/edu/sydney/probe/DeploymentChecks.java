package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import android.os.SystemClock;
import java.util.ArrayList;
import java.util.List;

public final class DeploymentChecks extends Instrumentation {
    private int checks;
    private void check(boolean value,String name) { checks++;if(!value) throw new AssertionError(name); }
    private void rejects(String json) { try { DeploymentCodec.decode(json);throw new AssertionError("Accepted: "+json); } catch(IllegalArgumentException expected) { checks++; } }
    @Override public void onCreate(Bundle args) { super.onCreate(args);start(); }
    @Override public void onStart() {
        Bundle out=new Bundle();
        try {
            String a=ProbePolicy.TRANSFER_PACKAGE,b=ProbePolicy.ROOM_PACKAGE;
            TwoStepSkill source=new TwoStepSkill(List.of(new SwitchSkill(a,a+":id/mainToggle",false,true),new SwitchSkill(a,a+":id/otherToggle",true,false)));
            DeploymentSkill s=new DeploymentSkill("11111111-1111-4111-8111-111111111111","22222222-2222-4222-8222-222222222222","",source,List.of("Lighting","Ventilation"),b,List.of(b+":id/ceiling",b+":id/airflow"));
            String json=DeploymentCodec.encode(s);
            check(json.equals(DeploymentCodec.encode(DeploymentCodec.decode(json))),"roundtrip");
            check(DeploymentCodec.decode(json).source.appPackage.equals(a),"original source package");
            check(!DeploymentCodec.decode(json).boundSkill().steps.get(1).defaultDesired,"default off preserved");
            for(String bad:List.of("{}",json+"{}",json.substring(0,json.length()-1),json.replace("\"schemaVersion\":3","\"schemaVersion\":3.0"),json.replace("\"schemaVersion\":3","\"schemaVersion\":\"3\""),json.replace("\"schemaVersion\":3","\"schemaVersion\":3,\"schemaVersion\":3"),json.replace("\"schemaVersion\":3","\"schemaVersion\":3,\"approved\":true"),json.replace("\"Lighting\"","null"),json.replace("\"Lighting\"","true"),json.replace("\"Lighting\"","\"Ventilation\""),json.replace("\"Lighting\"","\"Lighting\",\"Extra\""),json.replace("\"Lighting\",", ""),json.replace("airflow","ceiling"),json.replace(b+":id",a+":id"),json.replace("22222222-2222-4222-8222-222222222222","bad")," ".repeat(8193),"null","[]")) {
                check(!bad.equals(json),"negative payload mutation must change input");rejects(bad);
            }
            DeploymentStore store=new DeploymentStore(getTargetContext(),"deployment_checks");
            android.content.SharedPreferences prefs=getTargetContext().getSharedPreferences("deployment_checks",0);prefs.edit().clear().commit();
            try {
                check(store.importDraft(json),"import draft");check(store.active()==null,"import not approved");
                check(!store.review(json),"review before preflight blocked");
                store.checkResult(s,"READY");check(store.canReview(),"ready permits review");
                check(!store.review(json+" "),"stale dialog");check(store.review(json),"approve exact snapshot");
                check(store.history().size()==1,"history saved");
                check(store.importDraft(json),"reimport");check(!store.canReview(),"approval token not imported");
                check(store.active()!=null,"old approval preserved");
                store.checkResult(s,"READY");store.clearCheck();check(!store.canReview(),"reconnect invalidates");
                store.checkResult(s,"READY");prefs.edit().putLong("checkAt",SystemClock.elapsedRealtime()-60001).commit();check(!store.canReview(),"expired");
                store.checkResult(s,"READY");prefs.edit().putString("session","foreign").commit();check(!store.canReview(),"session");
                String changed=json.replace("Lighting","Other goal");
                try { store.importDraft(changed);throw new AssertionError("Mutated approved binding"); } catch(IllegalArgumentException expected) { checks++; }
                check(DeploymentCodec.encode(store.active()).equals(json),"unchanged approval");
                DeploymentSkill rebound=new DeploymentSkill(s.workflowId,"33333333-3333-4333-8333-333333333333",s.bindingId,source,s.roles,a,List.of(a+":id/mainToggle",a+":id/otherToggle"));
                String json2=DeploymentCodec.encode(rebound);check(store.importDraft(json2),"new version draft");
                store.checkResult(s,"READY");check(!store.canReview(),"old asynchronous response");
                store.checkResult(rebound,"READY");check(store.review(json2),"approve version");check(store.history().size()==2,"old version retained");
                check(store.activate(s.bindingId),"restore reviewed history");check(store.active().bindingId.equals(s.bindingId),"restored version");
                check(!store.activate("unknown"),"unreviewed ID cannot activate");
                prefs.edit().putString("approved."+s.bindingId,"{}").commit();check(store.active()==null,"corrupt approval fails closed");
            } finally { prefs.edit().clear().commit(); }
            out.putString("result","PASS checks="+checks);finish(-1,out);
        } catch(Throwable error) { out.putString("result","FAIL "+error);finish(0,out); }
    }
}
