package edu.sydney.probe;

import android.util.JsonReader;
import android.util.JsonToken;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Bounded v2 format. Imported booleans are evidence claims, not authorizations. */
public final class TwoStepCodec {
    private TwoStepCodec() { }
    public static String encode(TwoStepSkill skill) {
        try {
            JSONArray steps = new JSONArray();
            for (SwitchSkill step : skill.steps) steps.put(new JSONObject().put("resourceId",step.resourceId)
                    .put("before",step.demonstratedBefore).put("after",step.defaultDesired));
            return new JSONObject().put("schemaVersion",2).put("operation","SET_TWO_CHECKED")
                    .put("appPackage",skill.appPackage).put("steps",steps).toString();
        } catch (Exception e) { throw new IllegalArgumentException("Cannot encode",e); }
    }
    public static TwoStepSkill decode(String json) {
        try {
            if (json == null || json.length()>8192) throw new IllegalArgumentException("Size");
            JsonReader r = new JsonReader(new StringReader(json)); r.setLenient(false);
            Set<String> keys = new HashSet<>(); String pkg=null;
            List<String> ids=new ArrayList<>(); List<Boolean> before=new ArrayList<>(), after=new ArrayList<>();
            r.beginObject();
            while (r.hasNext()) {
                String key=r.nextName(); if (!keys.add(key)) throw new IllegalArgumentException("Duplicate");
                switch(key) {
                    case "schemaVersion":
                        if (r.peek()!=JsonToken.NUMBER || !"2".equals(r.nextString())) throw new IllegalArgumentException("Version"); break;
                    case "operation":
                        if (!"SET_TWO_CHECKED".equals(string(r))) throw new IllegalArgumentException("Operation"); break;
                    case "appPackage": pkg=string(r); break;
                    case "steps":
                        r.beginArray();
                        while(r.hasNext()) {
                            if(ids.size()>=2) throw new IllegalArgumentException("Count");
                            Set<String> fields=new HashSet<>(); String id=null; Boolean b=null,a=null;
                            r.beginObject();
                            while(r.hasNext()) {
                                String field=r.nextName(); if(!fields.add(field)) throw new IllegalArgumentException("Duplicate");
                                switch(field) {
                                    case "resourceId": id=string(r);break;
                                    case "before": b=bool(r);break;
                                    case "after": a=bool(r);break;
                                    default: throw new IllegalArgumentException("Unknown step field");
                                }
                            }
                            r.endObject();
                            if(!fields.equals(Set.of("resourceId","before","after"))) throw new IllegalArgumentException("Missing step field");
                            ids.add(id);before.add(b);after.add(a);
                        }
                        r.endArray();break;
                    default: throw new IllegalArgumentException("Unknown field");
                }
            }
            r.endObject();
            if(r.peek()!=JsonToken.END_DOCUMENT || !keys.equals(Set.of("schemaVersion","operation","appPackage","steps")))
                throw new IllegalArgumentException("Missing or trailing data");
            r.close(); List<SwitchSkill> steps=new ArrayList<>();
            for(int i=0;i<ids.size();i++) steps.add(new SwitchSkill(pkg,ids.get(i),before.get(i),after.get(i)));
            return new TwoStepSkill(steps);
        } catch(Exception e) { throw new IllegalArgumentException("Invalid two-step skill",e); }
    }
    private static String string(JsonReader r) throws Exception {
        if(r.peek()!=JsonToken.STRING) throw new IllegalArgumentException("Expected string"); return r.nextString();
    }
    private static boolean bool(JsonReader r) throws Exception {
        if(r.peek()!=JsonToken.BOOLEAN) throw new IllegalArgumentException("Expected boolean"); return r.nextBoolean();
    }
}
