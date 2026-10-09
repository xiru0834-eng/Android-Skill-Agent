package edu.sydney.probe;
import org.json.*;
import java.util.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Local evidence compiler and independent imported-skill structural checker. */
final class FlexibleWorkflowCodec {
    static final int LIMIT=262144;
    static Integer[] goals(JSONArray a)throws JSONException{return WorkflowCodec.requested(a);}
    static JSONArray array(Integer[] g){JSONArray a=new JSONArray();for(Integer v:g)a.put(v==null?JSONObject.NULL:v);return a;}
    static FlexibleWorkflow.State traceState(JSONObject trace)throws Exception{
        JSONObject initial=trace.getJSONObject("initial");
        FlexibleWorkflow.State state=new FlexibleWorkflow.State(initial.getString("page"),WorkflowCodec.concrete(initial.getJSONArray("saved")));
        for(int i=0;i<trace.getJSONArray("steps").length();i++){
            JSONObject step=trace.getJSONArray("steps").getJSONObject(i);String id=step.getString("id");
            Boolean desired=(id.contains("Power")||id.contains("Value"))?step.getJSONObject("after").getJSONObject("values").getBoolean(id):null;
            state.apply(id,desired);
        }return state;
    }
    static String resolve(FlexibleWorkflow.State state,JSONArray candidates,JSONObject after)throws Exception{
        List<String> ids=new ArrayList<>();for(int i=0;i<candidates.length();i++)ids.add(candidates.getString(i));
        WorkflowCodec.fields(after,"page","values","saved","dirty");
        Map<String,Boolean> values=new HashMap<>();JSONObject raw=after.getJSONObject("values");
        for(Iterator<String> it=raw.keys();it.hasNext();){String key=it.next();WorkflowCodec.require(raw.get(key) instanceof Boolean,"VALUE");values.put(key,raw.getBoolean(key));}
        JSONArray stored=after.getJSONArray("saved");int[] saved=stored.length()==0?new int[0]:WorkflowCodec.concrete(stored);
        return FlexibleWorkflow.resolve(state,ids,after.getString("page"),values,saved,after.getBoolean("dirty"));
    }
    static boolean matches(JSONObject s,FlexibleWorkflow.State state)throws JSONException{
        WorkflowCodec.fields(s,"page","values","saved","dirty");
        if(!state.page().equals(s.get("page"))||!Boolean.valueOf(state.dirty()).equals(s.get("dirty")))return false;
        JSONObject values=s.getJSONObject("values");Map<String,Boolean> expected=state.values();
        if(values.length()!=expected.size())return false;
        for(var e:expected.entrySet())if(!e.getValue().equals(values.opt(e.getKey())))return false;
        JSONArray saved=s.getJSONArray("saved");
        if(state.page().equals("overview")||state.page().equals("single"))return Arrays.equals(WorkflowCodec.concrete(saved),state.saved());
        return saved.length()==0;
    }
    static JSONObject compile(String raw){
        try{
            WorkflowCodec.checkJson(raw,LIMIT);JSONObject t=new JSONObject(raw);
            WorkflowCodec.fields(t,"kind","version","traceId","appPackage","appVersion","source","goal","end","error","initial","steps","final");
            WorkflowCodec.require("WORKFLOW_TRACE".equals(t.get("kind"))&&Integer.valueOf(2).equals(t.get("version")),"TRACE_VERSION");
            WorkflowCodec.require("STOPPED".equals(t.get("end"))&&"".equals(t.get("error")),"INCOMPLETE_TRACE");
            JSONObject initial=t.getJSONObject("initial");String start=initial.getString("page");
            FlexibleWorkflow.State state=new FlexibleWorkflow.State(start,WorkflowCodec.concrete(initial.getJSONArray("saved")));
            WorkflowCodec.require(matches(initial,state),"INITIAL_MISMATCH");
            JSONArray source=t.getJSONArray("steps"),steps=new JSONArray();long time=-1;
            WorkflowCodec.require(source.length()>0,"NO_STEPS");
            for(int i=0;i<source.length();i++){
                JSONObject s=source.getJSONObject(i);boolean inferred="UNIQUE_TRANSITION".equals(s.optString("attribution"));
                if(inferred)WorkflowCodec.fields(s,"id","before","after","eventTime","attribution","candidateIds");
                else WorkflowCodec.fields(s,"id","before","after","eventTime","attribution");
                WorkflowCodec.require((s.get("eventTime") instanceof Integer||s.get("eventTime") instanceof Long)&&s.getLong("eventTime")>time,"EVENT_ORDER");time=s.getLong("eventTime");
                WorkflowCodec.require(inferred||List.of("RESOURCE_ID","UNIQUE_LABEL").contains(s.get("attribution")),"ATTRIBUTION");
                WorkflowCodec.require(matches(s.getJSONObject("before"),state),"DISCONTINUOUS_TRACE");
                String id=s.getString("id"),before=state.page();Boolean desired=null;
                if(inferred)WorkflowCodec.require(id.equals(resolve(state,s.getJSONArray("candidateIds"),s.getJSONObject("after"))),"AMBIGUOUS_TRANSITION");
                if(id.contains("Power")||id.contains("Value")){
                    Object value=s.getJSONObject("after").getJSONObject("values").get(id);WorkflowCodec.require(value instanceof Boolean,"DESIRED");desired=(Boolean)value;
                    if(id.endsWith("Power"))WorkflowCodec.require(!desired.equals(state.values().get(id)),"NO_OBSERVED_CHANGE");
                }
                FlexibleWorkflow.Action a=state.apply(id,desired);
                WorkflowCodec.require(matches(s.getJSONObject("after"),state),"ACTION_EFFECT_MISMATCH");
                steps.put(new JSONObject().put("id",id).put("page",before).put("afterPage",state.page()).put("desired",desired==null?JSONObject.NULL:desired)
                    .put("sourceIndex",i+1).put("operation",a.operation).put("commitGoals",array(a.commitGoals)));
            }
            WorkflowCodec.require(state.complete()&&matches(t.getJSONObject("final"),state),"UNSAVED_OR_FINAL_MISMATCH");
            JSONObject skill=new JSONObject().put("kind","WORKFLOW_SKILL").put("version",3);
            for(String key:List.of("appPackage","appVersion","traceId","source","goal"))skill.put(key,t.get(key));
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(canonical(t).getBytes(StandardCharsets.UTF_8));StringBuilder hash=new StringBuilder();for(byte b:digest)hash.append(String.format(Locale.ROOT,"%02x",b&255));
            skill.put("traceSha256",hash.toString())
                .put("startPage",start).put("endPage",state.page()).put("steps",steps).put("finalGoals",array(state.goals()));
            return decode(skill);
        }catch(Exception e){throw new IllegalArgumentException("INVALID_FLEXIBLE_TRACE",e);}
    }
    static JSONObject decode(JSONObject s)throws Exception{
        WorkflowCodec.fields(s,"kind","version","appPackage","appVersion","traceId","traceSha256","source","goal","startPage","endPage","steps","finalGoals");
        WorkflowCodec.require("WORKFLOW_SKILL".equals(s.get("kind"))&&Integer.valueOf(3).equals(s.get("version")),"VERSION");
        WorkflowCodec.require(WorkflowUi.PKG.equals(s.get("appPackage")),"APP");
        WorkflowCodec.require(s.get("appVersion") instanceof String&&s.getString("appVersion").matches("[0-9]{1,12}"),"APP_VERSION");
        WorkflowCodec.require(s.get("traceId") instanceof String&&UUID.fromString(s.getString("traceId")).toString().equals(s.getString("traceId")),"TRACE_ID");
        WorkflowCodec.require(s.get("traceSha256") instanceof String&&s.getString("traceSha256").matches("[a-f0-9]{64}"),"HASH");
        WorkflowCodec.require(List.of("AUTOMATED","HUMAN_DECLARED").contains(s.get("source")),"SOURCE");
        WorkflowCodec.require(s.get("goal") instanceof String&&!s.getString("goal").isBlank()&&s.getString("goal").length()<=240,"GOAL");
        // Feasibility must not depend on a hard-coded demonstration initial state.
        // Runtime independently binds actual initial values and checks every precondition.
        try{simulate(s,new int[]{0,40,0,3});return s;}catch(Exception ignored){}
        for(int power:new int[]{0,1})for(int light:FlexibleWorkflow.OPTIONS[1])
            for(int fan:new int[]{0,1})for(int speed:FlexibleWorkflow.OPTIONS[3]){
                try{simulate(s,new int[]{power,light,fan,speed});return s;}catch(Exception ignored){}
            }
        throw new IllegalArgumentException("INFEASIBLE_ORDERED_PROCESS");
    }
    private static void simulate(JSONObject s,int[] initial)throws Exception{
        FlexibleWorkflow.State state=new FlexibleWorkflow.State(s.getString("startPage"),initial);
        JSONArray steps=s.getJSONArray("steps");WorkflowCodec.require(steps.length()>0,"NO_STEPS");
        for(int i=0;i<steps.length();i++){
            JSONObject step=steps.getJSONObject(i);WorkflowCodec.fields(step,"id","page","afterPage","desired","sourceIndex","operation","commitGoals");
            WorkflowCodec.require(state.page().equals(step.get("page"))&&Integer.valueOf(i+1).equals(step.get("sourceIndex")),"STEP_ORDER");
            Boolean desired=null;if(!step.isNull("desired")){WorkflowCodec.require(step.get("desired") instanceof Boolean,"DESIRED");desired=step.getBoolean("desired");}
            FlexibleWorkflow.Action a=state.apply(step.getString("id"),desired);
            WorkflowCodec.require(a.operation.equals(step.get("operation"))&&state.page().equals(step.get("afterPage")),"ACTION_METADATA");
            WorkflowCodec.require(Arrays.equals(a.commitGoals,goals(step.getJSONArray("commitGoals"))),"COMMIT_GOALS");
        }
        WorkflowCodec.require(state.complete()&&state.page().equals(s.get("endPage"))&&Arrays.equals(state.goals(),goals(s.getJSONArray("finalGoals"))),"FINAL_GOALS");
    }
    static String canonical(Object value)throws JSONException{
        if(value==null||value==JSONObject.NULL)return "null";
        if(value instanceof JSONObject){JSONObject o=(JSONObject)value;List<String> keys=new ArrayList<>();o.keys().forEachRemaining(keys::add);Collections.sort(keys);List<String> parts=new ArrayList<>();for(String k:keys)parts.add(quote(k)+":"+canonical(o.get(k)));return "{"+String.join(",",parts)+"}";}
        if(value instanceof JSONArray){JSONArray a=(JSONArray)value;List<String> parts=new ArrayList<>();for(int i=0;i<a.length();i++)parts.add(canonical(a.get(i)));return "["+String.join(",",parts)+"]";}
        if(value instanceof String)return quote((String)value);
        if(value instanceof Boolean||value instanceof Integer||value instanceof Long)return value.toString();
        throw new IllegalArgumentException("JSON_TYPE");
    }
    private static String quote(String v){
        StringBuilder b=new StringBuilder("\"");for(char c:v.toCharArray())switch(c){
            case '"':b.append("\\\"");break;case '\\':b.append("\\\\");break;
            case '\b':b.append("\\b");break;case '\f':b.append("\\f");break;case '\n':b.append("\\n");break;case '\r':b.append("\\r");break;case '\t':b.append("\\t");break;
            default:if(c<32)b.append(String.format(Locale.ROOT,"\\u%04x",(int)c));else b.append(c);
        }return b.append('"').toString();
    }
}
