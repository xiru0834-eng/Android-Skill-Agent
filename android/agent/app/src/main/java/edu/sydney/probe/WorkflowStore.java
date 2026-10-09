package edu.sydney.probe;

import android.content.*;
import org.json.*;
import java.util.*;

/** Device-local approval never appears in exported JSON. Legacy stores untouched. */
final class WorkflowStore {
    private final SharedPreferences prefs;
    private final Context context;
    WorkflowStore(Context c){context=c;prefs=c.getSharedPreferences("recorded_workflows",0);}
    String draft(){return prefs.getString("draft",null);}
    String approved(){return storageUnconfirmed()?null:prefs.getString("approved",null);}
    boolean storageUnconfirmed(){return prefs.getBoolean("storageUnconfirmed",false);}
    boolean stage(String raw){String value=WorkflowCodec.decode(raw).toString();return prefs.edit().putString("draft",value).commit();}
    boolean review(String expected) {
        if(expected==null||!expected.equals(draft())||!sameVersion(expected))return false;
        String fallback="Workflow "+WorkflowCodec.decode(expected).optString("traceSha256").substring(0,8);
        for(var item:entries())if(item.raw.equals(expected))return reviewNamed(expected,item.name);
        return reviewNamed(expected,fallback);
    }
    boolean reviewNamed(String expected,String name) {
        if(name==null||name.isBlank()||name.length()>60||expected==null||!expected.equals(draft())||!sameVersion(expected))return false;
        return writeReviewed(expected,name,null);
    }
    /** Local compiler review: validate everything before changing draft or approvals. */
    boolean reviewCompiled(String expected,String name){return writeReviewed(expected,name,null);}
    private boolean writeReviewed(String expected,String name,String pendingExpected){
        if(expected==null||active()||!sameVersion(expected))return false;
        if(pendingExpected!=null&&!pendingExpected.equals(pendingNamed()))return false;
        try {
            var next=NamedWorkflowCodec.entry(TeachingInput.name(name),expected);
            var items=NamedWorkflowPolicy.add(entries(),next);JSONArray all=new JSONArray();
            for(var item:items)all.put(new JSONObject(NamedWorkflowCodec.encode(item)));
            var editor=prefs.edit().putString("draft",next.raw).putString("library",all.toString()).putString("approved",next.raw).putString("namedSkill",next.raw).putString("name",next.name).remove("storageUnconfirmed");
            if(pendingExpected!=null)editor.remove("pendingNamed");
            if(editor.commit())return true;
            // commit(false) may have changed process memory: block execution, not claim rollback.
            prefs.edit().putBoolean("storageUnconfirmed",true).commit();return false;
        }catch(Exception e){return false;}
    }
    private boolean active(){ProbeService s=ProbeService.current();return s!=null&&(s.workflowRunning()||s.workflowRecorder().active());}
    List<NamedWorkflowPolicy.Entry> entries(){
        try {
            List<NamedWorkflowPolicy.Entry> all=new ArrayList<>();JSONArray stored=new JSONArray(prefs.getString("library","[]"));
            if(stored.length()>20)throw new IllegalArgumentException("LIBRARY_FULL");
            for(int i=0;i<stored.length();i++)all=NamedWorkflowPolicy.add(all,NamedWorkflowCodec.decode(stored.getJSONObject(i).toString()));
            if(approved()!=null){var legacy=NamedWorkflowCodec.entry(name(),approved());boolean found=false;
                for(var e:all)if(e.id.equals(legacy.id)){if(!e.raw.equals(legacy.raw))throw new IllegalArgumentException("EVIDENCE_CONFLICT");found=true;}
                if(!found)all=NamedWorkflowPolicy.add(all,legacy);
            }return all;
        }catch(Exception e){throw new IllegalArgumentException("LIBRARY_INVALID",e);}
    }
    NamedWorkflowPolicy.Entry find(String id){for(var e:entries())if(e.id.equals(id))return e;return null;}
    boolean activate(NamedWorkflowPolicy.Entry expected){
        if(storageUnconfirmed()||active()||expected==null||!sameVersion(expected.raw))return false;
        var current=find(expected.id);if(current==null||!current.raw.equals(expected.raw)||!current.name.equals(expected.name))return false;
        return prefs.edit().putString("approved",current.raw).putString("namedSkill",current.raw).putString("name",current.name).commit();
    }
    String pendingNamed(){return prefs.getString("pendingNamed",null);}
    boolean stageNamed(String raw){if(active())return false;String valid=NamedWorkflowCodec.encode(NamedWorkflowCodec.decode(raw));return prefs.edit().putString("pendingNamed",valid).commit();}
    boolean reviewImported(String expected){
        if(expected==null||!expected.equals(pendingNamed())||active())return false;
        var item=NamedWorkflowCodec.decode(expected);
        return writeReviewed(item.raw,item.name,expected);
    }
    String name(){return approved()!=null&&approved().equals(prefs.getString("namedSkill",null))?prefs.getString("name","Transfer Bench"):"Transfer Bench";}
    boolean sameVersion(String raw) {
        try{return WorkflowCodec.decode(raw).getString("appVersion").equals(Long.toString(context.getPackageManager().getPackageInfo(WorkflowUi.PKG,0).getLongVersionCode()));}
        catch(Exception e){return false;}
    }
    String result(){return prefs.getString("result","尚未运行 / Not run");}
    void result(JSONObject r){prefs.edit().putString("result",r.toString()).commit();}
}
