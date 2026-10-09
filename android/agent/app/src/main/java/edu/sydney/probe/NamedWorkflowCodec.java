package edu.sydney.probe;
import org.json.*;

/** Portable metadata only. Device-local review is never exported. */
final class NamedWorkflowCodec {
    static NamedWorkflowPolicy.Entry entry(String name,String skill){
        try{JSONObject s=WorkflowCodec.decode(skill);return new NamedWorkflowPolicy.Entry(s.getString("traceSha256"),name,s.toString());}
        catch(Exception e){throw new IllegalArgumentException("INVALID_NAMED_SKILL",e);}
    }
    static String encode(NamedWorkflowPolicy.Entry e){
        try{return new JSONObject().put("kind","NAMED_WORKFLOW").put("version",1).put("name",e.name).put("skill",WorkflowCodec.decode(e.raw)).toString();}
        catch(JSONException error){throw new IllegalArgumentException("INVALID_PACKAGE",error);}
    }
    static NamedWorkflowPolicy.Entry decode(String raw){
        try{
            WorkflowCodec.checkJson(raw,FlexibleWorkflowCodec.LIMIT);JSONObject o=new JSONObject(raw);
            WorkflowCodec.fields(o,"kind","version","name","skill");
            WorkflowCodec.require("NAMED_WORKFLOW".equals(o.get("kind"))&&Integer.valueOf(1).equals(o.get("version"))&&o.get("name") instanceof String,"PACKAGE_SCHEMA");
            return entry(o.getString("name"),o.getJSONObject("skill").toString());
        }catch(Exception e){throw new IllegalArgumentException("INVALID_NAMED_PACKAGE",e);}
    }
}
