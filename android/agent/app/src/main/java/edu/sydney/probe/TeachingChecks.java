package edu.sydney.probe;

import android.app.Instrumentation;
import android.content.*;
import android.os.Bundle;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

/** Diagnostic tests use an isolated preference namespace; never user approvals. */
public final class TeachingChecks extends Instrumentation {
    private String raw;private int passed;
    private void check(boolean v,String reason){if(!v)throw new AssertionError(reason);passed++;}
    @Override public void onCreate(Bundle args){super.onCreate(args);raw=new String(Base64.decode(args.getString("trace"),Base64.DEFAULT),StandardCharsets.UTF_8);start();}
    @Override public void onStart(){Bundle result=new Bundle();final String testName="task2_diagnostic_"+UUID.randomUUID().toString().replace("-","");
        Context actual=getTargetContext();SharedPreferences isolated=actual.getSharedPreferences(testName,0);
        Context context=new ContextWrapper(actual){@Override public SharedPreferences getSharedPreferences(String name,int mode){return isolated;}};
        try{
            JSONObject t=new JSONObject(raw);t.put("appVersion",Long.toString(actual.getPackageManager().getPackageInfo(WorkflowUi.PKG,0).getLongVersionCode()));
            String a=FlexibleWorkflowCodec.compile(t.toString()).toString();
            t.put("goal","Separate diagnostic evidence");String b=FlexibleWorkflowCodec.compile(t.toString()).toString();
            WorkflowStore store=new WorkflowStore(context);
            check(store.reviewCompiled(a,"First diagnostic"),"initial save");
            check(store.entries().size()==1&&store.approved().equals(a),"saved identity");
            Map<String,?> before=new HashMap<>(isolated.getAll());
            check(!store.reviewCompiled(b,"First diagnostic"),"duplicate name must fail");
            check(before.equals(isolated.getAll()),"duplicate save changed draft/library/approval");
            check(!store.reviewCompiled(b,"x".repeat(61)),"long name must fail");
            check(before.equals(isolated.getAll()),"long name wrote preferences");
            String pending=NamedWorkflowCodec.encode(NamedWorkflowCodec.entry("First diagnostic",b));
            check(store.stageNamed(pending),"stage import");before=new HashMap<>(isolated.getAll());
            check(!store.reviewImported(pending),"conflicting import must fail");
            check(before.equals(isolated.getAll()),"rejected import changed draft or pending");
            check(!store.reviewImported(pending+" "),"stale pending rejected");
            check(before.equals(isolated.getAll()),"stale pending wrote preferences");
            pending=NamedWorkflowCodec.encode(NamedWorkflowCodec.entry("Second diagnostic",b));
            check(store.stageNamed(pending),"stage second import");
            check(store.reviewImported(pending),"save imported review");
            check(store.pendingNamed()==null&&store.entries().size()==2&&store.approved().equals(b)&&store.draft().equals(b),"import not one coherent state");
            WorkflowStore reopened=new WorkflowStore(context);
            check(reopened.approved().equals(b)&&reopened.entries().size()==2,"reopen mismatch");
            check(reopened.reviewCompiled(b,"Second diagnostic")&&reopened.entries().size()==2,"idempotent save");
            JSONObject changed=new JSONObject(b);changed.put("appVersion","999999999");before=new HashMap<>(isolated.getAll());
            check(!reopened.reviewCompiled(changed.toString(),"wrong version"),"version mismatch");
            check(before.equals(isolated.getAll()),"version rejection wrote preferences");
            // Inject commit(false) at the adapter boundary; not an actual disk-fault experiment.
            SharedPreferences failure=(SharedPreferences)java.lang.reflect.Proxy.newProxyInstance(SharedPreferences.class.getClassLoader(),new Class[]{SharedPreferences.class},(proxy,method,args)->{
                if(!method.getName().equals("edit"))return method.invoke(isolated,args);
                SharedPreferences.Editor target=isolated.edit();
                return java.lang.reflect.Proxy.newProxyInstance(SharedPreferences.Editor.class.getClassLoader(),new Class[]{SharedPreferences.Editor.class},(p,m,v)->{
                    if(m.getName().equals("commit")){target.commit();return false;}
                    Object returned=m.invoke(target,v);return returned==target?p:returned;
                });
            });
            Context faultContext=new ContextWrapper(actual){@Override public SharedPreferences getSharedPreferences(String name,int mode){return failure;}};
            WorkflowStore faulty=new WorkflowStore(faultContext);
            check(!faulty.reviewCompiled(b,"Second diagnostic"),"failed commit reported saved");
            check(faulty.storageUnconfirmed()&&faulty.approved()==null,"unconfirmed storage usable");
            check(!faulty.activate(faulty.entries().get(0)),"activate after failed commit");
            check(store.reviewCompiled(b,"Second diagnostic")&&!store.storageUnconfirmed(),"fresh confirmed review cannot recover");
            String recorded=TeachingRecordView.actions(new JSONObject(raw),true);
            String guide=TeachingGuide.render(a,true);
            if(t.getJSONObject("initial").getString("page").equals("single")){
                check(!recorded.contains("return to overview"),"record summary fabricated navigation");
                check(!guide.contains("return to overview"),"guide fabricated navigation");
            }
            result.putString("result","PASS teaching checks="+passed+"; isolated preferences; commit failure injected; user approvals untouched");finish(-1,result);
        }catch(Throwable e){result.putString("error",e.toString());finish(1,result);}
        finally{actual.deleteSharedPreferences(testName);}
    }
}
