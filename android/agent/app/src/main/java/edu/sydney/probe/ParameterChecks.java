package edu.sydney.probe;

import android.app.Instrumentation;
import android.content.*;
import android.os.Bundle;
import org.json.*;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Android contracts in an isolated namespace. No GUI inputs, model calls or real approvals. */
public final class ParameterChecks extends Instrumentation {
    private Bundle args;
    private int checks;
    private final JSONArray rows=new JSONArray();
    interface Check {void run() throws Exception;}
    private void ok(boolean yes,String label)throws Exception {if(!yes)throw new AssertionError(label);checks++;rows.put(new JSONObject().put("case",label).put("passed",true));}
    private void bad(Check test,String label)throws Exception {boolean rejected=false;try{test.run();}catch(IllegalArgumentException e){rejected=true;}ok(rejected,label);}
    private JSONObject call(String skill,String device,Object value)throws Exception {
        return new JSONObject().put("skill",skill).put("args",new JSONObject().put("device",device).put(ParameterSkillCodec.argument(skill),value));
    }
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);args=arguments;start();}
    @Override public void onStart(){
        Bundle out=new Bundle();Context actual=getTargetContext();String space="parameter_diagnostic_"+UUID.randomUUID().toString().replace("-","");
        File folder=new File(actual.getCacheDir(),space);
        Context isolated=new ContextWrapper(actual){
            @Override public SharedPreferences getSharedPreferences(String name,int mode){return actual.getSharedPreferences(space,mode);}
            @Override public File getFilesDir(){return folder;}
        };
        SharedPreferences prefs=isolated.getSharedPreferences("recorded_workflows",0);
        try{
            NamedWorkflowPolicy.Entry original=new WorkflowStore(actual).find(args.getString("sourceId"));
            if(original==null)throw new AssertionError("Missing reviewed fixture source");
            var manager=(android.view.accessibility.AccessibilityManager)actual.getSystemService(Context.ACCESSIBILITY_SERVICE);
            ok(manager.getInstalledAccessibilityServiceList().stream().anyMatch(info->info.getResolveInfo().serviceInfo.packageName.equals(actual.getPackageName())
                &&(info.flags&android.accessibilityservice.AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS)!=0),"binding context includes non-actionable containers");
            var source=NamedWorkflowCodec.entry(original.name,original.raw);
            ok(folder.mkdir(),"create isolated package namespace");
            String oldRun=ExecutionResultData.latestRunId(isolated);
            var rejection=ParameterEntryEvidence.record(isolated,"UNSUPPORTED_VALUE");
            ok(rejection.getString("status").equals("REJECTED")&&rejection.getString("failureStage").equals("validation")&&!rejection.getBoolean("formalStarted"),"entry rejection has separate typed receipt");
            ok(java.util.Objects.equals(oldRun,ExecutionResultData.latestRunId(isolated)),"entry refusal does not replace formal run result");
            for(File temporary:folder.listFiles())temporary.delete();
            ok(prefs.edit().putString("library",new JSONArray().put(new JSONObject(NamedWorkflowCodec.encode(source))).toString())
                .putString("approved",source.raw).putString("namedSkill",source.raw).putString("name",source.name).commit(),"isolated reviewed source");
            String binding=ParameterBindingStore.localSnapshot(isolated,source);
            ok(folder.list().length==0,"local binding needs zero package files");
            ok(binding.equals(ParameterBindingStore.localSnapshot(isolated,source)),"stable local binding");
            JSONObject exported=ParameterBindingStore.packageFor(source);
            ok(exported.getInt("version")==2,"v2 parameter package");
            JSONObject fanSchema=exported.getJSONArray("skillSchemas").getJSONObject(2);
            ok(fanSchema.getJSONObject("parameters").getJSONObject("level").getInt("max")==Integer.MAX_VALUE,"fan semantic schema independent from three-level UI");
            ok(exported.getJSONObject("sourceEvidence").getJSONObject("originalWorkflow").toString().equals(WorkflowCodec.decode(source.raw).toString()),"original demonstration retained exactly");
            String schema=exported.getJSONArray("skillSchemas").toString();
            ok(!schema.contains("resource_id")&&!schema.contains("wfLamp")&&!schema.contains("transferlab")&&!schema.contains("screen"),"schema excludes environment identifiers");
            ok(exported.getJSONObject("environmentBinding").getJSONArray("targets").getJSONObject(0).getJSONArray("selectors").length()>0,"package retains environment selectors");
            var already=new ParameterExecution(isolated,source,new JSONArray().put(call("SetBrightness","bedroom_light",80)));
            ok(already.noActionRequired(new int[]{0,80,1,3}),"no action only for satisfied ordered call");
            ok(!already.noActionRequired(new int[]{0,60,1,3}),"new parameter requires action");
            var opposed=new ParameterExecution(isolated,source,new JSONArray().put(call("SetPower","bedroom_light","on")).put(call("SetPower","bedroom_light","off")));
            ok(!opposed.noActionRequired(new int[]{0,80,1,3}),"opposite ordered calls cannot shortcut on final goal");
            JSONArray catalog=ParameterSkillCodec.catalog(ParameterSkillCodec.binding(source.raw));
            int cases=0;
            for(int value:new int[]{20,40,60,80,100}){
                var calls=new JSONArray().put(call("SetBrightness","bedroom_light",value));
                var invocation=new ParameterExecution(isolated,source,calls);
                var plan=WorkflowCodec.decode(invocation.plan);
                ok(plan.getJSONArray("finalGoals").getInt(1)==value,"brightness "+value+" exact");
                ok(plan.getJSONArray("finalGoals").isNull(0)&&plan.getJSONArray("finalGoals").isNull(2)&&plan.getJSONArray("finalGoals").isNull(3),"brightness "+value+" preserves unrelated goals");
                ok(invocation.current()&&plan.getString("source").equals("AUTOMATED"),"brightness "+value+" authorization and provenance");cases++;
            }
            for(String device:List.of("bedroom_light","bedroom_fan"))for(String state:List.of("on","off")){
                var calls=new JSONArray().put(call("SetPower",device,state));
                var invocation=new ParameterExecution(isolated,source,calls);
                int field=device.equals("bedroom_light")?0:2;
                ok(WorkflowCodec.decode(invocation.plan).getJSONArray("finalGoals").getInt(field)==(state.equals("on")?1:0),device+" "+state);cases++;
            }
            for(int level:new int[]{1,2,3}){
                var invocation=new ParameterExecution(isolated,source,new JSONArray().put(call("SetFanSpeed","bedroom_fan",level)));
                ok(WorkflowCodec.decode(invocation.plan).getJSONArray("finalGoals").getInt(3)==level,"fan speed "+level);cases++;
            }
            var repeated=new JSONArray().put(call("SetBrightness","bedroom_light",20)).put(call("SetPower","bedroom_fan","on"))
                .put(call("SetBrightness","bedroom_light",100));
            var invocation=new ParameterExecution(isolated,source,repeated);
            var plan=WorkflowCodec.decode(invocation.plan);
            ok(plan.getJSONArray("finalGoals").getInt(1)==100&&plan.getJSONArray("finalGoals").getInt(2)==1,"last repeated target and joint goals");
            ok(invocation.audit().getJSONArray("calls").length()==3,"ordered repeated calls not discarded");
            ok(invocation.audit().getString("bindingSource").equals("LOCAL_REVIEWED_SOURCE")&&!invocation.audit().getBoolean("requiresPackageFile"),"audited local no-file route");
            for(Object invalid:List.of(-1,0,55,101,"80",80.0,true)){
                bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray().put(call("SetBrightness","bedroom_light",invalid))),"reject brightness "+invalid+"/"+invalid.getClass().getSimpleName());cases++;
            }
            for(Object invalid:List.of(0,4,"2",2.0,true)){
                bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray().put(call("SetFanSpeed","bedroom_fan",invalid))),"reject speed "+invalid+"/"+invalid.getClass().getSimpleName());cases++;
            }
            bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray().put(call("SetPower","bedroom_light","ON"))),"reject noncanonical power");
            bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray().put(call("SetPower","unknown","on"))),"reject unknown entity");
            bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray().put(call("SetBrightness","bedroom_fan",80))),"reject incompatible capability");
            bad(()->ParameterSkillCodec.calls(new JSONArray().put(new JSONObject().put("skill","SetTemperature").put("args",new JSONObject().put("device","bedroom_ac").put("celsius",28)))),"reject unbound temperature (not GUI capability)");
            bad(()->ParameterSkillCodec.compile(source.raw,new JSONArray()),"reject empty invocation");
            bad(()->ParameterSkillCodec.calls(new JSONArray().put(call("SetPower","bedroom_light","on").put("x",10))),"reject injected coordinates");
            var extra=call("SetBrightness","bedroom_light",80);extra.getJSONObject("args").put("state","on");
            bad(()->ParameterSkillCodec.calls(new JSONArray().put(extra)),"reject extra argument");
            JSONObject response=new JSONObject().put("request_id","contract").put("status","invoke").put("calls",repeated).put("message","Review");
            ok(ParameterSkillCodec.validateResponse(response.toString(),"contract",catalog).getJSONArray("calls").length()==3,"model response exact contract");
            JSONArray semanticCatalog=ParameterSkillCodec.semanticCatalog(ParameterSkillCodec.binding(source.raw));
            ok(SemanticParameterCodec.catalog(semanticCatalog).entities.entities.size()==2,"local adapter advertises only its two bound entities");
            ok(SemanticParameterCodec.response(response.toString(),"contract",semanticCatalog).getJSONArray("calls").length()==3,"v2 semantic response matches reviewed local capabilities");
            bad(()->ParameterSkillCodec.validateResponse(response.toString(),"other",catalog),"reject wrong request ID");
            bad(()->ParameterSkillCodec.validateResponse(new JSONObject(response.toString()).put("calls",new JSONArray().put(call("SetBrightness","bedroom_light",55))).toString(),"contract",catalog),"model cannot round unsupported value");
            var englishText=new ParameterText.Snapshot("  Set light to 80 percent  ");
            ok(englishText.text.equals("Set light to 80 percent")&&englishText.current("  Set light to 80 percent  "),"unchanged English with spaces remains current");
            ok(!englishText.current(englishText.text),"edited raw text invalidates request snapshot");
            var chineseText=new ParameterText.Snapshot("  把卧室灯调到80%  ");
            ok(chineseText.text.equals("把卧室灯调到80%")&&chineseText.current("  把卧室灯调到80%  "),"unchanged Chinese with spaces remains current");
            ok(ParameterText.checked("灯".repeat(240)).length()==240,"parameter text accepts 240 UTF16 units");
            bad(()->ParameterText.checked("灯".repeat(241)),"parameter text rejects 241 UTF16 units before API");
            bad(()->ParameterText.checked("Set light\non"),"parameter text rejects internal control before API");
            bad(()->ParameterText.checked("\uD83D\uDE00".repeat(121)),"parameter text rejects 242 emoji UTF16 units before API");
            ok(prefs.edit().putBoolean("storageUnconfirmed",true).commit(),"inject isolated unconfirmed storage");
            bad(()->ParameterBindingStore.localSnapshot(isolated,source),"unconfirmed storage rejected at entry");
            ok(!invocation.current(),"unconfirmed storage revokes invocation");
            prefs.edit().remove("storageUnconfirmed").commit();
            ok(invocation.current(),"isolated approval restored");
            var renamed=NamedWorkflowCodec.entry("Renamed",source.raw);
            bad(()->ParameterBindingStore.localSnapshot(isolated,renamed),"unreviewed name rejected");
            prefs.edit().putString("library","[]").remove("approved").commit();
            ok(!invocation.current(),"removed source revokes invocation");
            bad(()->ParameterBindingStore.localSnapshot(isolated,source),"removed source rejected");
            prefs.edit().putString("library",new JSONArray().put(new JSONObject(NamedWorkflowCodec.encode(source))).toString()).putString("approved",source.raw).commit();
            ok(folder.list().length==0,"parameter calls never wrote package");
            File optional=new File(folder,"parameter-skill-"+source.id+".json");
            try(var stream=new java.io.FileOutputStream(optional)){stream.write("{}".getBytes(StandardCharsets.UTF_8));}
            ok(binding.equals(ParameterBindingStore.localSnapshot(isolated,source)),"local route explicitly independent of optional export");
            bad(()->ParameterBindingStore.checked(isolated,source),"optional package still strictly validated");
            ParameterBindingStore.save(isolated,source);
            ok(new JSONObject(ParameterBindingStore.checked(isolated,source)).getInt("version")==2,"new package exact validation");
            // Reconstruct the documented v1 shape in this isolated test namespace only.
            JSONObject legacy=new JSONObject(exported.toString()).put("version",1);
            for(int i=0;i<legacy.getJSONArray("skillSchemas").length();i++){
                JSONObject row=legacy.getJSONArray("skillSchemas").getJSONObject(i);row.remove("preconditions");row.remove("successCondition");
                String name=row.getString("name");row.put("goal",name.equals("SetPower")?"power == state":name.equals("SetBrightness")?"brightness == percent":"fanSpeed == level");
                if(name.equals("SetFanSpeed"))row.getJSONObject("parameters").getJSONObject("level").put("max",3);
            }
            for(int i=0;i<legacy.getJSONObject("environmentBinding").getJSONArray("targets").length();i++)legacy.getJSONObject("environmentBinding").getJSONArray("targets").getJSONObject(i).remove("selectors");
            try(var stream=new java.io.FileOutputStream(optional)){stream.write(legacy.toString().getBytes(StandardCharsets.UTF_8));}
            ok(new JSONObject(ParameterBindingStore.checked(isolated,source)).getInt("version")==1,"exact historical v1 package remains readable");
            ok(new WorkflowStore(actual).find(source.id).raw.equals(original.raw),"real source unchanged");
            out.putString("result","PASS ParameterChecks checks="+checks+"; structuralCases="+cases+"; GUI inputs=0; paid requests=0");
            out.putString("rows",rows.toString());finish(-1,out);
        }catch(Throwable error){out.putString("error",error.toString());out.putString("rows",rows.toString());finish(1,out);}
        finally{prefs.edit().clear().commit();File[] temporary=folder.listFiles();if(temporary!=null)for(File file:temporary)file.delete();folder.delete();}
    }
}
