package edu.sydney.probe;

import org.json.*;
import java.util.*;

/** v2 wire contracts use only semantic definitions and entity-specific domains. */
final class SemanticParameterCodec {
    static final int REQUEST_LIMIT=65536,RESPONSE_LIMIT=16384;
    static final class Catalog {
        final SemanticSkills.Catalog entities;
        final SemanticCapabilities.Environment domains;
        Catalog(SemanticSkills.Catalog entities,SemanticCapabilities.Environment domains){this.entities=entities;this.domains=domains;}
    }
    private static void need(boolean value,String reason){WorkflowCodec.require(value,reason);}
    static String text(String value,int limit){
        need(value!=null&&value.length()<=limit&&!value.isBlank(),"TEXT");
        for(int i=0;i<value.length();i++){
            char c=value.charAt(i);need(!Character.isISOControl(c),"TEXT");
            if(Character.isHighSurrogate(c)){need(i+1<value.length()&&Character.isLowSurrogate(value.charAt(++i)),"TEXT");}
            else need(!Character.isLowSurrogate(c),"TEXT");
        }return value;
    }
    static Catalog catalog(JSONArray raw)throws Exception {
        need(raw!=null&&raw.length()>0&&raw.length()<=128,"CATALOG_SIZE");
        need(raw.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length<=24000,"CATALOG_BYTES");
        List<SemanticSkills.Entity> entities=new ArrayList<>();Map<String,Map<String,SemanticCapabilities.Domain>> domains=new LinkedHashMap<>();
        for(int i=0;i<raw.length();i++){
            JSONObject row=raw.getJSONObject(i);WorkflowCodec.fields(row,"device","name","aliases","capabilities");
            need(row.opt("device") instanceof String&&row.opt("name") instanceof String,"ENTITY_TYPE");
            String device=row.getString("device");text(row.getString("name"),80);
            JSONArray aliases=row.getJSONArray("aliases");need(aliases.length()<=16,"ALIASES");List<String> labels=new ArrayList<>();
            for(int a=0;a<aliases.length();a++){need(aliases.get(a) instanceof String,"ALIAS_TYPE");labels.add(text(aliases.getString(a),80));}
            need(new HashSet<>(labels).size()==labels.size(),"ALIAS_DUPLICATE");
            JSONArray capabilities=row.getJSONArray("capabilities");need(capabilities.length()>0&&capabilities.length()<=8,"CAPABILITIES");
            Map<String,SemanticCapabilities.Domain> caps=new LinkedHashMap<>();
            for(int c=0;c<capabilities.length();c++){
                JSONObject cap=capabilities.getJSONObject(c);WorkflowCodec.fields(cap,"skill","domain");
                need(cap.opt("skill") instanceof String,"CAPABILITY_TYPE");String skill=cap.getString("skill");
                SemanticSkills.definition(skill);need(!caps.containsKey(skill),"CAPABILITY_DUPLICATE");
                JSONObject domain=cap.getJSONObject("domain");SemanticCapabilities.Domain value;
                if(domain.has("values")){
                    WorkflowCodec.fields(domain,"values");JSONArray values=domain.getJSONArray("values");List<Object> options=new ArrayList<>();
                    for(int n=0;n<values.length();n++)options.add(values.get(n));value=SemanticCapabilities.Domain.values(options);
                }else{
                    WorkflowCodec.fields(domain,"min","max","step");
                    need(domain.opt("min") instanceof Integer&&domain.opt("max") instanceof Integer&&domain.opt("step") instanceof Integer,"DOMAIN_INTEGER");
                    value=SemanticCapabilities.Domain.range(domain.getInt("min"),domain.getInt("max"),domain.getInt("step"));
                }caps.put(skill,value);
            }
            entities.add(new SemanticSkills.Entity(device,row.getString("name"),labels,caps.keySet()));
            need(!domains.containsKey(device),"DUPLICATE_ENTITY");domains.put(device,caps);
        }
        return new Catalog(new SemanticSkills.Catalog(entities),new SemanticCapabilities.Environment("wire_catalog",domains));
    }
    static List<SemanticSkills.Call> calls(JSONArray raw)throws Exception {
        need(raw!=null&&raw.length()>0&&raw.length()<=SemanticSkills.MAX_CALLS,"CALL_COUNT");List<SemanticSkills.Call> calls=new ArrayList<>();
        for(int i=0;i<raw.length();i++){
            JSONObject call=raw.getJSONObject(i);WorkflowCodec.fields(call,"skill","args");need(call.opt("skill") instanceof String,"SKILL_TYPE");
            String skill=call.getString("skill");JSONObject args=call.getJSONObject("args");Map<String,Object> values=new HashMap<>();
            for(Iterator<String> it=args.keys();it.hasNext();){String key=it.next();values.put(key,args.get(key));}
            calls.add(SemanticSkills.parse(skill,values));
        }return List.copyOf(calls);
    }
    static JSONObject response(String raw,String requestId,JSONArray source)throws Exception {
        WorkflowCodec.checkJson(raw,RESPONSE_LIMIT);JSONObject data=new JSONObject(raw);WorkflowCodec.fields(data,"request_id","status","calls","message");
        need(requestId.equals(data.opt("request_id"))&&data.opt("message") instanceof String,"RESPONSE_MISMATCH");text(data.getString("message"),500);
        need(data.opt("status") instanceof String&&List.of("invoke","clarify","reject").contains(data.getString("status")),"STATUS");
        Catalog catalog=catalog(source);JSONArray rawCalls=data.getJSONArray("calls");
        if(data.getString("status").equals("invoke"))SemanticCapabilities.compile(catalog.entities,catalog.domains,calls(rawCalls));
        else need(rawCalls.length()==0,"UNEXPECTED_CALLS");
        return data;
    }
}
