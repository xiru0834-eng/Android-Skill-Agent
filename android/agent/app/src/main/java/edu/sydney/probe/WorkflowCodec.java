package edu.sydney.probe;

import android.util.*;
import org.json.*;
import java.io.StringReader;
import java.util.*;

/** Imports only a bounded, explicit route for the experimental three-page app. */
final class WorkflowCodec {
    static void require(boolean ok,String reason){if(!ok)throw new IllegalArgumentException(reason);}
    static JSONObject decode(String raw) {
        try {
            require(raw!=null&&raw.length()<=FlexibleWorkflowCodec.LIMIT,"SIZE");
            checkJson(raw,FlexibleWorkflowCodec.LIMIT);
            JSONObject s=new JSONObject(raw);
            if(Integer.valueOf(3).equals(s.opt("version")))return FlexibleWorkflowCodec.decode(s);
            require(raw.length()<=8192,"SIZE");
            fields(s,"kind","version","appPackage","appVersion","traceId","traceSha256","source","goal","steps","finalGoals");
            require("WORKFLOW_SKILL".equals(s.get("kind"))&&(Integer.valueOf(1).equals(s.get("version"))||Integer.valueOf(2).equals(s.get("version"))),"VERSION");
            require(WorkflowUi.PKG.equals(s.get("appPackage")),"APP");
            require(s.get("appVersion") instanceof String&&s.getString("appVersion").matches("[0-9]{1,12}"),"APP_VERSION");
            require(s.get("traceId") instanceof String&&UUID.fromString(s.getString("traceId")).toString().equals(s.getString("traceId")),"TRACE_ID");
            require(s.get("traceSha256") instanceof String&&s.getString("traceSha256").matches("[a-f0-9]{64}"),"HASH");
            require(List.of("AUTOMATED","HUMAN_DECLARED").contains(s.get("source")),"SOURCE");
            require(s.get("goal") instanceof String&&!s.getString("goal").isBlank()&&s.getString("goal").length()<=240,"GOAL");
            JSONArray goals=s.getJSONArray("finalGoals");require(goals.length()==4,"GOAL_COUNT");
            Integer[] requested=requested(goals);JSONArray steps=s.getJSONArray("steps");
            require(WorkflowGoals.valid(s.getInt("version"),steps.length(),requested),"GOAL_SCOPE");Set<String> groups=new HashSet<>();
            for(int offset=0;offset<steps.length();offset+=4) {
                String entry=steps.getJSONObject(offset).getString("id");String group=entry.equals("wfOpenLamp")?"Lamp":entry.equals("wfOpenFan")?"Fan":"";
                require(!group.isEmpty()&&groups.add(group),"ROUTE");String page=group.toLowerCase(Locale.ROOT);int index=group.equals("Lamp")?0:2;
                require(requested[index]!=null,"ROUTE_SCOPE");
                String[] ids={"wfOpen"+group,"wf"+group+"Power","wf"+group+"Value"+goals.getInt(index+1),"wf"+group+"Save"};
                for(int pos=0;pos<4;pos++) {
                    JSONObject step=steps.getJSONObject(offset+pos);fields(step,"id","page","afterPage","desired","sourceIndex");
                    require(ids[pos].equals(step.get("id"))&&(pos==0?"overview":page).equals(step.get("page"))&&(pos==3?"overview":page).equals(step.get("afterPage")),"STEP_ROUTE");
                    require(Integer.valueOf(offset+pos+1).equals(step.get("sourceIndex")),"SOURCE_INDEX");
                    if(pos==1||pos==2)require(Boolean.valueOf(pos==2||goals.getInt(index)==1).equals(step.get("desired")),"DESIRED");
                    else require(step.isNull("desired"),"NAV_DESIRED");
                }
            }
            return s;
        }catch(Exception e){throw new IllegalArgumentException("INVALID_WORKFLOW",e);}
    }
    static Integer[] requested(JSONArray goals)throws JSONException {
        require(goals.length()==4,"GOAL_COUNT");Integer[] out=new Integer[4];
        for(int i=0;i<4;i++)if(!goals.isNull(i)){require(goals.get(i) instanceof Integer,"GOAL_TYPE");out[i]=goals.getInt(i);}return out;
    }
    static int[] concrete(JSONArray values)throws JSONException {
        require(values.length()==4,"GOAL_COUNT");int[] out=new int[4];
        for(int i=0;i<4;i++){require(values.get(i) instanceof Integer,"GOAL_TYPE");out[i]=values.getInt(i);}return out;
    }
    static void checkJson(String raw,int limit) throws Exception {
        require(raw!=null&&raw.length()<=limit,"SIZE");
        JsonReader reader=new JsonReader(new StringReader(raw));reader.setLenient(false);scan(reader,0);
        require(reader.peek()==JsonToken.END_DOCUMENT,"TRAILING_DATA");reader.close();
    }
    static void fields(JSONObject object,String... names) {
        Set<String> actual=new HashSet<>();object.keys().forEachRemaining(actual::add);
        require(actual.equals(Set.of(names)),"FIELDS");
    }
    private static void scan(JsonReader reader,int depth) throws Exception {
        require(depth<8,"DEPTH");
        switch(reader.peek()) {
            case BEGIN_OBJECT:reader.beginObject();Set<String> names=new HashSet<>();while(reader.hasNext()){require(names.add(reader.nextName()),"DUPLICATE");scan(reader,depth+1);}reader.endObject();break;
            case BEGIN_ARRAY:reader.beginArray();while(reader.hasNext())scan(reader,depth+1);reader.endArray();break;
            case STRING:case NUMBER:reader.nextString();break;
            case BOOLEAN:reader.nextBoolean();break;
            case NULL:reader.nextNull();break;
            default:throw new IllegalArgumentException("JSON_TOKEN");
        }
    }
}
