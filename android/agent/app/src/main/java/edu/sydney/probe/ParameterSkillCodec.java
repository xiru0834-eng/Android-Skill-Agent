package edu.sydney.probe;
import org.json.*;
import java.util.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** JSON boundaries and lab environment bindings. Semantic definitions stay in ParameterSkills. */
final class ParameterSkillCodec {
    static ParameterSkills.Binding binding(String raw)throws Exception{
        JSONObject source=WorkflowCodec.decode(raw);
        WorkflowCodec.require(source.getInt("version")==3&&source.getString("startPage").equals(source.getString("endPage")),"PARAMETER_SOURCE_ROUTE");
        Set<String> ids=new HashSet<>();JSONArray steps=source.getJSONArray("steps");
        for(int i=0;i<steps.length();i++)ids.add(steps.getJSONObject(i).getString("id"));
        return new ParameterSkills.Binding(source.getString("startPage"),ids);
    }
    static JSONArray catalog(ParameterSkills.Binding binding)throws Exception{
        JSONArray result=new JSONArray();
        for(String device:List.of("bedroom_light","bedroom_fan")){
            JSONArray skills=new JSONArray();for(String name:ParameterSkills.NAMES)if(binding.supports(name,device))skills.put(name);
            if(skills.length()==0)continue;
            JSONArray values=new JSONArray();for(int n:device.equals("bedroom_light")?FlexibleWorkflow.OPTIONS[1]:FlexibleWorkflow.OPTIONS[3])values.put(n);
            result.put(new JSONObject().put("device",device).put("skills",skills).put("values",values));
        }
        WorkflowCodec.require(result.length()>0,"NO_PARAMETER_CAPABILITY");return result;
    }
    static String argument(String name){return SemanticSkills.definition(name).argument;}
    static JSONArray semanticCatalog(ParameterSkills.Binding binding)throws Exception {
        // Only this existing lab adapter knows lab entities. The v2 wire codec does not.
        JSONArray old=catalog(binding),result=new JSONArray();
        for(int i=0;i<old.length();i++){
            JSONObject row=old.getJSONObject(i);String device=row.getString("device");JSONArray capabilities=new JSONArray();
            for(int c=0;c<row.getJSONArray("skills").length();c++){
                String skill=row.getJSONArray("skills").getString(c);
                JSONArray values=skill.equals("SetPower")?new JSONArray().put("on").put("off"):row.getJSONArray("values");
                capabilities.put(new JSONObject().put("skill",skill).put("domain",new JSONObject().put("values",values)));
            }
            boolean lamp=device.equals("bedroom_light");
            result.put(new JSONObject().put("device",device).put("name",lamp?"卧室灯 / Bedroom light":"卧室风扇 / Bedroom fan")
                .put("aliases",lamp?new JSONArray().put("灯").put("light").put("lamp"):new JSONArray().put("风扇").put("fan"))
                .put("capabilities",capabilities));
        }SemanticParameterCodec.catalog(result);return result;
    }
    static List<ParameterSkills.Call> calls(JSONArray raw)throws Exception{
        WorkflowCodec.require(raw.length()>0&&raw.length()<=ParameterSkills.MAX_CALLS,"CALL_COUNT");
        List<ParameterSkills.Call> calls=new ArrayList<>();
        for(int i=0;i<raw.length();i++){
            JSONObject call=raw.getJSONObject(i);WorkflowCodec.fields(call,"skill","args");
            WorkflowCodec.require(call.opt("skill") instanceof String&&ParameterSkills.NAMES.contains(call.getString("skill")),"UNKNOWN_SKILL");
            JSONObject args=call.getJSONObject("args");String name=call.getString("skill");WorkflowCodec.fields(args,"device",argument(name));
            WorkflowCodec.require(args.opt("device") instanceof String,"DEVICE_TYPE");
            calls.add(new ParameterSkills.Call(name,args.getString("device"),args.get(argument(name))));
        }return calls;
    }
    static JSONObject validateResponse(String raw,String requestId,JSONArray catalog)throws Exception{
        WorkflowCodec.checkJson(raw,8192);JSONObject response=new JSONObject(raw);WorkflowCodec.fields(response,"request_id","status","calls","message");
        WorkflowCodec.require(requestId.equals(response.opt("request_id"))&&response.opt("message") instanceof String&&!response.getString("message").isEmpty()&&response.getString("message").length()<=500,"RESPONSE_MISMATCH");
        String status=response.getString("status");WorkflowCodec.require(List.of("invoke","clarify","reject").contains(status),"STATUS");
        JSONArray rawCalls=response.getJSONArray("calls");
        if(!status.equals("invoke")){WorkflowCodec.require(rawCalls.length()==0,"UNEXPECTED_CALLS");return response;}
        for(var call:calls(rawCalls)){
            JSONObject device=null;for(int i=0;i<catalog.length();i++)if(catalog.getJSONObject(i).getString("device").equals(call.device))device=catalog.getJSONObject(i);
            WorkflowCodec.require(device!=null,"UNBOUND_DEVICE");boolean found=false;
            for(int i=0;i<device.getJSONArray("skills").length();i++)if(device.getJSONArray("skills").getString(i).equals(call.skill))found=true;
            WorkflowCodec.require(found,"UNBOUND_CAPABILITY");
            if(call.skill.equals("SetPower"))WorkflowCodec.require(call.value instanceof String&&List.of("on","off").contains(call.value),"POWER_STATE");
            else{WorkflowCodec.require(call.value instanceof Integer,"PARAMETER_INTEGER");found=false;
                for(int i=0;i<device.getJSONArray("values").length();i++)if(Integer.valueOf(device.getJSONArray("values").getInt(i)).equals(call.value))found=true;
                WorkflowCodec.require(found,"UNSUPPORTED_VALUE");}
        }return response;
    }
    static JSONObject compile(String sourceRaw,JSONArray rawCalls)throws Exception{
        JSONObject source=WorkflowCodec.decode(sourceRaw);var binding=binding(sourceRaw);var plan=ParameterSkills.compile(binding,calls(rawCalls));
        JSONArray steps=new JSONArray();for(var step:plan.steps)steps.put(new JSONObject().put("id",step.id).put("page",step.page).put("afterPage",step.afterPage).put("desired",step.desired==null?JSONObject.NULL:step.desired)
            .put("sourceIndex",steps.length()+1).put("operation",step.operation).put("commitGoals",FlexibleWorkflowCodec.array(step.commitGoals)));
        // This is an independently generated runtime plan, NOT a new observed demonstration.
        JSONObject result=new JSONObject(source.toString()).put("traceId",UUID.randomUUID().toString()).put("source","AUTOMATED")
            .put("goal","Parameterized semantic calls; see PARAMETER_CALLS audit").put("steps",steps).put("finalGoals",FlexibleWorkflowCodec.array(plan.goals));
        result.put("traceSha256",hash(new JSONObject().put("kind","PARAMETERIZED_PLAN").put("sourceSkillId",source.getString("traceSha256")).put("calls",rawCalls).put("plan",result).toString()));
        return WorkflowCodec.decode(result.toString());
    }
    static String hash(String raw)throws Exception{
        byte[] bytes=MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));StringBuilder out=new StringBuilder();for(byte value:bytes)out.append(String.format(Locale.ROOT,"%02x",value&255));return out.toString();
    }
}
