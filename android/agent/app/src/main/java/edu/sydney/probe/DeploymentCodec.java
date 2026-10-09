package edu.sydney.probe;

import android.util.JsonReader;
import android.util.JsonToken;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** v3 is a data-only deployment envelope; sourceJson is the unchanged strict v2 provenance. */
public final class DeploymentCodec {
    private static final Set<String> FIELDS=Set.of("schemaVersion","workflowId","bindingId","parentBindingId","sourceJson","roles","targetPackage","targetIds");
    public static String encode(DeploymentSkill s) {
        try { return new JSONObject().put("schemaVersion",3).put("workflowId",s.workflowId).put("bindingId",s.bindingId)
                .put("parentBindingId",s.parentBindingId).put("sourceJson",TwoStepCodec.encode(s.source))
                .put("roles",new JSONArray(s.roles)).put("targetPackage",s.targetPackage).put("targetIds",new JSONArray(s.targetIds)).toString();
        } catch(Exception e) { throw new IllegalArgumentException("Cannot encode deployment",e); }
    }
    public static DeploymentSkill decode(String json) {
        try {
            if(json==null || json.length()>8192) throw new IllegalArgumentException("Size");
            JsonReader r=new JsonReader(new StringReader(json));r.setLenient(false);
            Set<String> seen=new HashSet<>();Map<String,String> values=new HashMap<>();
            List<String> roles=null,ids=null;r.beginObject();
            while(r.hasNext()) {
                String k=r.nextName();if(!FIELDS.contains(k) || !seen.add(k)) throw new IllegalArgumentException("Unknown/duplicate field");
                if(k.equals("schemaVersion")) { if(r.peek()!=JsonToken.NUMBER || !"3".equals(r.nextString())) throw new IllegalArgumentException("Version"); }
                else if(k.equals("roles")) roles=strings(r);
                else if(k.equals("targetIds")) ids=strings(r);
                else values.put(k,string(r));
            }
            r.endObject();if(!seen.equals(FIELDS) || r.peek()!=JsonToken.END_DOCUMENT) throw new IllegalArgumentException("Missing/trailing data");r.close();
            return new DeploymentSkill(values.get("workflowId"),values.get("bindingId"),values.get("parentBindingId"),
                    TwoStepCodec.decode(values.get("sourceJson")),roles,values.get("targetPackage"),ids);
        } catch(Exception e) { throw new IllegalArgumentException("Invalid deployment file",e); }
    }
    private static String string(JsonReader r) throws Exception { if(r.peek()!=JsonToken.STRING) throw new IllegalArgumentException("String required");return r.nextString(); }
    private static List<String> strings(JsonReader r) throws Exception {
        List<String> out=new ArrayList<>();r.beginArray();while(r.hasNext()) { if(out.size()==2) throw new IllegalArgumentException("Two slots only");out.add(string(r)); }r.endArray();return out;
    }
    private DeploymentCodec() {}
}
