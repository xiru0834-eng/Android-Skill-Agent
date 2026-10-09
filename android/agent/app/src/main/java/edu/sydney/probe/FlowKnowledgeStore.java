package edu.sydney.probe;
import android.content.Context;
import org.json.*;
import java.util.*;

/** Local reviewed immutable knowledge. Imported bytes have no execution rights. */
final class FlowKnowledgeStore {
    private final Context context;private final PortableSkillStore files;
    FlowKnowledgeStore(Context context){this.context=context;files=new PortableSkillStore(context);}
    private static void need(boolean ok,String reason){if(!ok)throw new IllegalArgumentException(reason);}
    static String canonical(Object value)throws Exception{
        if(value instanceof JSONObject){var o=(JSONObject)value;var keys=new TreeSet<String>();o.keys().forEachRemaining(keys::add);var rows=new ArrayList<String>();for(String k:keys)rows.add(JSONObject.quote(k)+":"+canonical(o.get(k)));return "{"+String.join(",",rows)+"}";}
        if(value instanceof JSONArray){var a=(JSONArray)value;var rows=new ArrayList<String>();for(int i=0;i<a.length();i++)rows.add(canonical(a.get(i)));return "["+String.join(",",rows)+"]";}
        return value instanceof String?JSONObject.quote((String)value):String.valueOf(value);
    }
    JSONObject decode(String raw)throws Exception{
        WorkflowCodec.checkJson(raw,131072);var o=new JSONObject(raw);
        need("android_published_flow_v1".equals(o.getString("schema"))&&o.get("execution_authority").equals(false),"KNOWLEDGE_SCHEMA");
        need(o.getString("source_publication").matches("[a-f0-9]{64}"),"SOURCE_PUBLICATION");
        need(PortableSkillCodec.hash(canonical(o.getJSONObject("flow"))).equals(o.getString("flow_hash")),"FLOW_HASH");
        var cat=o.getJSONArray("catalog");need(cat.length()==1&&cat.getJSONObject(0).getString("flow_hash").equals(o.getString("flow_hash")),"CATALOG_MISMATCH");
        need(cat.getJSONObject(0).getString("id").equals(o.getJSONObject("flow").getString("id"))&&cat.getJSONObject(0).getString("version").equals(o.getJSONObject("flow").getString("version")),"CATALOG_MISMATCH");
        var plan=o.getJSONObject("compiled_template");need(o.getString("flow_hash").equals(plan.getString("flow_hash")),"FLOW_HASH");
        Set<String> writes=new TreeSet<>();var a=plan.getJSONArray("actual_write_set");for(int i=0;i<a.length();i++)writes.add(a.getString(i));
        new FlowAndroidRunner(plan,files.approved(),writes,"PUBLISHED_USER_TASK");
        return o;
    }
    String incoming()throws Exception{try(var f=context.openFileInput("published-flow-incoming.json")){return SkillFiles.read(f,131072);}}
    void write(String name,String raw)throws Exception{
        need(Set.of("published-flow-local.json","flow-user-selection.json","flow-user-result.json").contains(name),"FLOW_FILE_SCOPE");
        need(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8).length<=262144,"FLOW_FILE_LIMIT");
        var file=new android.util.AtomicFile(new java.io.File(context.getFilesDir(),name));java.io.FileOutputStream stream=null;
        try{stream=file.startWrite();stream.write(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8));file.finishWrite(stream);}catch(Exception e){if(stream!=null)file.failWrite(stream);throw e;}
    }
    void approve(String raw)throws Exception{decode(raw);write("published-flow-local.json",raw);need(context.getSharedPreferences("flow_knowledge_review",0).edit().putString("raw_sha256",PortableSkillCodec.hash(raw)).commit(),"FLOW_APPROVAL_STORAGE");}
    String approvedRaw()throws Exception{
        String raw;try(var f=context.openFileInput("published-flow-local.json")){raw=SkillFiles.read(f,131072);}
        need(FlowDigest.sha256(raw).equals(context.getSharedPreferences("flow_knowledge_review",0).getString("raw_sha256","")),"LOCAL_FLOW_REVIEW_REQUIRED");return raw;
    }
    JSONObject approved()throws Exception{return decode(approvedRaw());}
    boolean reviewedBytesUnchanged(FlowReviewedBytes pinned){
        try{
            if(pinned==null)return false;
            String raw;try(var input=context.openFileInput("published-flow-local.json")){raw=SkillFiles.read(input,131072);}
            return pinned.matches(raw,context.getSharedPreferences("flow_knowledge_review",0).getString("raw_sha256",""));
        }
        catch(Exception error){return false;}
    }
    static void replace(JSONObject plan,JSONArray path,Object value)throws Exception{
        Object current=plan;for(int i=0;i<path.length()-1;i++)current=current instanceof JSONObject?((JSONObject)current).get(path.getString(i)):((JSONArray)current).get(path.getInt(i));
        int n=path.length()-1;if(current instanceof JSONObject)((JSONObject)current).put(path.getString(n),value);else ((JSONArray)current).put(path.getInt(n),value);
    }
    static JSONObject response(String raw,String id,JSONArray catalog)throws Exception{
        WorkflowCodec.checkJson(raw,131072);var r=new JSONObject(raw);WorkflowCodec.fields(r,"request_id","status","message","flow_hash","arguments","plan");
        need(id.equals(r.getString("request_id"))&&r.get("message") instanceof String&&r.getString("message").length()<=500,"RESPONSE_MISMATCH");
        String status=r.getString("status");need(Set.of("invoke","clarify","reject").contains(status),"STATUS");
        if(!status.equals("invoke"))need(r.getString("flow_hash").isEmpty()&&r.getJSONArray("arguments").length()==0&&r.isNull("plan"),"NON_INVOKE_PAYLOAD");
        else need(catalog.length()==1&&r.getString("flow_hash").equals(catalog.getJSONObject(0).getString("flow_hash")),"UNKNOWN_FLOW");return r;
    }
    JSONObject validateResponse(JSONObject knowledge,JSONObject response)throws Exception{
        need(knowledge.getString("flow_hash").equals(response.getString("flow_hash")),"FLOW_CHANGED");
        JSONObject args=new JSONObject();var specs=knowledge.getJSONObject("flow").getJSONArray("inputs");var rows=response.getJSONArray("arguments");need(rows.length()==specs.length(),"INPUT_FIELDS");
        for(int i=0;i<rows.length();i++){
            var row=rows.getJSONObject(i);WorkflowCodec.fields(row,"name","type","value");String name=row.getString("name");need(!args.has(name),"DUPLICATE_INPUT");
            JSONObject spec=null;for(int j=0;j<specs.length();j++)if(specs.getJSONObject(j).getString("name").equals(name))spec=specs.getJSONObject(j);need(spec!=null&&spec.getString("type").equals(row.getString("type"))&&row.get("value") instanceof String,"INPUT_FIELDS");
            String value=row.getString("value");
            if(spec.getString("type").equals("integer")){
                need(value.matches("-?(0|[1-9][0-9]{0,8})"),"INPUT_TYPE");int v=Integer.parseInt(value);need(v>=spec.getInt("minimum")&&v<=spec.getInt("maximum")&&(v-spec.getInt("minimum"))%spec.getInt("step")==0,"INPUT_RANGE");args.put(name,v);
            }else if(spec.getString("type").equals("entity")){
                need(canonical(knowledge.getJSONObject("template_inputs").getJSONObject(name)).equals(canonical(new JSONObject().put("entity_id",value))),"ENTITY_NOT_REVIEWED");args.put(name,value);
            }else throw new IllegalArgumentException("INPUT_TYPE_UNSUPPORTED");
        }
        var expected=new JSONObject(knowledge.getJSONObject("compiled_template").toString());var slots=knowledge.getJSONArray("parameter_slots");for(int i=0;i<slots.length();i++){var s=slots.getJSONObject(i);replace(expected,s.getJSONArray("path"),args.get(s.getString("input")));}
        var proposed=new JSONObject(response.getJSONObject("plan").toString());
        for(String field:List.of("task_id","task_hash","host_device_id","authorization_ref","cancellation_token_ref")){
            need(proposed.get(field) instanceof String,"TASK_METADATA_TYPE");proposed.put(field,expected.get(field));
        }
        need(canonical(expected).equals(canonical(proposed)),"COMPILED_FLOW_CHANGED");return new JSONObject(response.getJSONObject("plan").toString());
    }
}
