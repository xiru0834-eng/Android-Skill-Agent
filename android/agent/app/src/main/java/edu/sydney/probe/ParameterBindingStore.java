package edu.sydney.probe;
import android.content.Context;
import android.util.AtomicFile;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.List;

/** Saved parameter package is separate from the immutable demonstration library. */
final class ParameterBindingStore {
    /** Local calls use reviewed local evidence, never an exported file as authorization. */
    static String localSnapshot(Context context,NamedWorkflowPolicy.Entry source)throws Exception{
        WorkflowStore store=new WorkflowStore(context);
        WorkflowCodec.require(!store.storageUnconfirmed(),"STORAGE_UNCONFIRMED");
        WorkflowCodec.require(source!=null,"NO_PARAMETER_SOURCE");
        var current=store.find(source.id);
        WorkflowCodec.require(current!=null&&current.raw.equals(source.raw)&&current.name.equals(source.name)
            &&store.sameVersion(source.raw),"PARAMETER_BINDING_CHANGED");
        return FlexibleWorkflowCodec.canonical(packageFor(current));
    }
    static JSONObject packageFor(NamedWorkflowPolicy.Entry source)throws Exception{
        return packageFor(source,false);
    }
    private static JSONObject packageFor(NamedWorkflowPolicy.Entry source,boolean legacy)throws Exception{
        JSONObject original=WorkflowCodec.decode(source.raw);var binding=ParameterSkillCodec.binding(source.raw);
        JSONArray schemas=new JSONArray(),devices=ParameterSkillCodec.catalog(binding),targets=new JSONArray();
        for(String name:ParameterSkills.NAMES){
            JSONObject value=name.equals("SetPower")?new JSONObject().put("type","string").put("enum",new JSONArray().put("on").put("off")):
                new JSONObject().put("type","integer").put("min",name.equals("SetBrightness")?0:1).put("max",name.equals("SetBrightness")?100:3);
            schemas.put(new JSONObject().put("name",name).put("parameters",new JSONObject().put("device","semantic-device").put(ParameterSkillCodec.argument(name),value))
                .put("goal",name.equals("SetPower")?"power == state":name.equals("SetBrightness")?"brightness == percent":"fanSpeed == level"));
            if(!legacy){
                var definition=SemanticSkills.definition(name);
                if(definition.kind.equals("integer"))value.put("min",definition.min).put("max",definition.max);
                schemas.getJSONObject(schemas.length()-1).put("goal",definition.property+" == "+definition.argument)
                    .put("preconditions",new JSONArray().put("entity exists").put("entity supports capability"))
                    .put("successCondition","fresh observed property equals requested argument");
            }
        }
        for(int i=0;i<devices.length();i++){
            JSONObject row=devices.getJSONObject(i);String group=binding.group(row.getString("device"));
            JSONObject controls=new JSONObject().put("save",new JSONObject().put("role","button").put("resource_id",WorkflowUi.PKG+":id/wf"+group+"Save"));
            if(binding.supports("SetPower",row.getString("device")))controls.put("power",new JSONObject().put("role","checkable").put("resource_id",WorkflowUi.PKG+":id/wf"+group+"Power"));
            JSONArray options=new JSONArray();for(int n:group.equals("Lamp")?FlexibleWorkflow.OPTIONS[1]:FlexibleWorkflow.OPTIONS[3])options.put(new JSONObject().put("value",n).put("role","radio").put("resource_id",WorkflowUi.PKG+":id/wf"+group+"Value"+n));
            controls.put("valueOptions",options);if(binding.startPage.equals("overview"))controls.put("entry",new JSONObject().put("role","button").put("resource_id",WorkflowUi.PKG+":id/wfOpen"+group));
            targets.put(new JSONObject().put("device",row.getString("device")).put("availableSkills",row.getJSONArray("skills")).put("controls",controls));
            if(!legacy){
                JSONArray selectors=new JSONArray();List<String> ids=new java.util.ArrayList<>();
                ids.add("wf"+group+"Save");if(binding.supports("SetPower",row.getString("device")))ids.add("wf"+group+"Power");
                for(int n:group.equals("Lamp")?FlexibleWorkflow.OPTIONS[1]:FlexibleWorkflow.OPTIONS[3])ids.add("wf"+group+"Value"+n);
                if(binding.startPage.equals("overview"))ids.add("wfOpen"+group);
                for(String id:ids){
                    var target=TransferLabSelectors.target(id);
                    selectors.put(new JSONObject().put("semanticTarget",target.key).put("resource_id",target.packageName+":id/"+target.resourceId)
                        .put("text",target.text).put("contentDescription",target.description).put("className",target.className)
                        .put("role",target.role).put("containerText",target.scopeText).put("pages",new JSONArray(new java.util.TreeSet<>(target.pages))));
                }targets.getJSONObject(targets.length()-1).put("selectors",selectors);
            }
        }
        return new JSONObject().put("kind","PARAMETER_SKILL_PACKAGE").put("version",legacy?1:2).put("name",source.name+" / parameters").put("skillSchemas",schemas)
            .put("environmentBinding",new JSONObject().put("appPackage",WorkflowUi.PKG).put("appVersion",original.getString("appVersion")).put("startPage",binding.startPage).put("targets",targets).put("adapter","KNOWN_TRANSFERLAB_V6"))
            .put("sourceEvidence",new JSONObject().put("skillId",source.id).put("source",original.getString("source")).put("originalWorkflow",original))
            .put("approvalPortable",false);
    }
    private static AtomicFile file(Context context,String id){
        WorkflowCodec.require(id!=null&&id.matches("[a-f0-9]{64}"),"SOURCE_ID");
        return new AtomicFile(new File(context.getFilesDir(),"parameter-skill-"+id+".json"));
    }
    static void save(Context context,NamedWorkflowPolicy.Entry source)throws Exception{
        byte[] data=packageFor(source).toString().getBytes(StandardCharsets.UTF_8);AtomicFile file=file(context,source.id);FileOutputStream out=file.startWrite();
        try{out.write(data);file.finishWrite(out);}catch(Exception e){file.failWrite(out);throw e;}
    }
    static String checked(Context context,NamedWorkflowPolicy.Entry source)throws Exception{
        byte[] bytes;try(InputStream in=file(context,source.id).openRead()){bytes=in.readNBytes(524289);}
        WorkflowCodec.require(bytes.length<=524288,"PARAMETER_PACKAGE_SIZE");
        String raw=new String(bytes,StandardCharsets.UTF_8);WorkflowCodec.checkJson(raw,524288);
        JSONObject decoded=new JSONObject(raw);String canonical=FlexibleWorkflowCodec.canonical(decoded);
        WorkflowCodec.require(decoded.optInt("version")==1||decoded.optInt("version")==2,"PARAMETER_PACKAGE_VERSION");
        WorkflowCodec.require(canonical.equals(FlexibleWorkflowCodec.canonical(packageFor(source,decoded.optInt("version")==1))),"PARAMETER_PACKAGE_CHANGED");return canonical;
    }
}
