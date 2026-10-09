package edu.sydney.probe;

import android.util.JsonReader;
import android.util.JsonToken;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/** Strict evidence format independent from executable skill file versions. */
public final class TraceCodec {
    public static final int MAX_BYTES=65536;
    private static final Set<String> FIELDS=Set.of("kind","schemaVersion","traceId","appPackage","appVersion","goal","source","end",
            "observationScope","visualEvidence","steps","finalState","unattributedChanges","unsupportedClicks","overflowClicks");
    public static String encode(TraceBundle b) {
        try {
            JSONArray steps=new JSONArray();int index=0;
            for(TraceBundle.Step s:b.steps) steps.put(new JSONObject().put("index",++index).put("targetId",s.targetId)
                    .put("eventTime",s.eventTime).put("before",s.before==null?JSONObject.NULL:s.before)
                    .put("after",s.after==null?JSONObject.NULL:s.after).put("outcome",s.outcome.name()));
            JSONObject state=new JSONObject();for(Map.Entry<String,String> e:new TreeMap<>(b.finalState).entrySet()) state.put(e.getKey(),e.getValue());
            String json=new JSONObject().put("kind","TRACE_BUNDLE").put("schemaVersion",1).put("traceId",b.traceId)
                    .put("appPackage",b.appPackage).put("appVersion",b.appVersion).put("goal",b.goal).put("source",b.source.name())
                    .put("end",b.end.name()).put("observationScope","TARGET_STATES_ONLY").put("visualEvidence","NOT_COLLECTED")
                    .put("steps",steps).put("finalState",state).put("unattributedChanges",b.unattributedChanges)
                    .put("unsupportedClicks",b.unsupportedClicks).put("overflowClicks",b.overflowClicks).toString();
            if(json.getBytes(StandardCharsets.UTF_8).length>MAX_BYTES) throw new IllegalArgumentException("Size");return json;
        } catch(Exception error) { throw new IllegalArgumentException("Cannot encode trace",error); }
    }
    public static TraceBundle decode(String json) {
        try {
            if(json==null || json.length()>MAX_BYTES || json.getBytes(StandardCharsets.UTF_8).length>MAX_BYTES) throw new IllegalArgumentException("Size");
            try(JsonReader r=new JsonReader(new StringReader(json))) {
                r.setLenient(false);Set<String> seen=new HashSet<>();Map<String,String> values=new HashMap<>();
                List<TraceBundle.Step> steps=null;Map<String,String> state=null;int unmatched=0,unsupported=0,overflow=0;
                r.beginObject();while(r.hasNext()) {
                    String key=r.nextName();if(!FIELDS.contains(key) || !seen.add(key)) throw new IllegalArgumentException("Unknown/duplicate field");
                    switch(key) {
                        case "schemaVersion": if(number(r)!=1) throw new IllegalArgumentException("Version");break;
                        case "steps": steps=steps(r);break;
                        case "finalState": state=state(r);break;
                        case "unattributedChanges": unmatched=count(r);break;
                        case "unsupportedClicks": unsupported=count(r);break;
                        case "overflowClicks": overflow=count(r);break;
                        default: values.put(key,string(r));
                    }
                }
                r.endObject();if(!seen.equals(FIELDS) || r.peek()!=JsonToken.END_DOCUMENT
                        || !"TRACE_BUNDLE".equals(values.get("kind")) || !"TARGET_STATES_ONLY".equals(values.get("observationScope"))
                        || !"NOT_COLLECTED".equals(values.get("visualEvidence"))) throw new IllegalArgumentException("Incomplete trace");
                return new TraceBundle(values.get("traceId"),values.get("appPackage"),values.get("appVersion"),values.get("goal"),
                        TraceBundle.Source.valueOf(values.get("source")),TraceBundle.End.valueOf(values.get("end")),steps,state,unmatched,unsupported,overflow);
            }
        } catch(Exception error) { throw new IllegalArgumentException("Invalid trace evidence",error); }
    }
    private static List<TraceBundle.Step> steps(JsonReader r) throws Exception {
        List<TraceBundle.Step> out=new ArrayList<>();Set<String> fields=Set.of("index","targetId","eventTime","before","after","outcome");
        r.beginArray();while(r.hasNext()) {
            if(out.size()>=30) throw new IllegalArgumentException("Step count");
            Set<String> seen=new HashSet<>();String id=null,before=null,after=null,outcome=null;long time=0;
            r.beginObject();while(r.hasNext()) {
                String key=r.nextName();if(!fields.contains(key) || !seen.add(key)) throw new IllegalArgumentException("Step fields");
                switch(key) {
                    case "index": if(number(r)!=out.size()+1) throw new IllegalArgumentException("Step sequence");break;
                    case "eventTime": time=number(r);break;
                    case "targetId": id=string(r);break;
                    case "before": before=nullable(r);break;
                    case "after": after=nullable(r);break;
                    case "outcome": outcome=string(r);break;
                }
            }
            r.endObject();if(!seen.equals(fields)) throw new IllegalArgumentException("Missing step field");
            out.add(new TraceBundle.Step(id,time,before,after,DemoTrace.Outcome.valueOf(outcome)));
        }r.endArray();return out;
    }
    private static Map<String,String> state(JsonReader r) throws Exception {
        Map<String,String> out=new HashMap<>();r.beginObject();while(r.hasNext()) {
            if(out.size()>=100) throw new IllegalArgumentException("State count");
            String key=r.nextName();if(out.containsKey(key)) throw new IllegalArgumentException("Duplicate state");out.put(key,string(r));
        }r.endObject();return out;
    }
    private static String string(JsonReader r) throws Exception { if(r.peek()!=JsonToken.STRING) throw new IllegalArgumentException("String required");return r.nextString(); }
    private static String nullable(JsonReader r) throws Exception { if(r.peek()==JsonToken.NULL) { r.nextNull();return null; }return string(r); }
    private static long number(JsonReader r) throws Exception {
        if(r.peek()!=JsonToken.NUMBER) throw new IllegalArgumentException("Number required");String value=r.nextString();
        if(!value.matches("0|[1-9][0-9]{0,18}")) throw new IllegalArgumentException("Nonnegative integer required");return Long.parseLong(value);
    }
    private static int count(JsonReader r) throws Exception { long n=number(r);if(n>Integer.MAX_VALUE) throw new IllegalArgumentException("Count overflow");return (int)n; }
    private TraceCodec() {}
}
