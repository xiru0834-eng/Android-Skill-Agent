package edu.sydney.probe;
import android.app.Instrumentation;
import android.os.Bundle;
import android.util.Base64;
import org.json.*;
import java.nio.charset.StandardCharsets;

/** Diagnostic codec checks only. Never writes approval or dispatches GUI input. */
public final class FlexibleWorkflowChecks extends Instrumentation {
    private String raw;private int passed;
    @Override public void onCreate(Bundle args){super.onCreate(args);raw=new String(Base64.decode(args.getString("trace"),Base64.DEFAULT),StandardCharsets.UTF_8);start();}
    private void rejectSkill(String value){try{WorkflowCodec.decode(value);}catch(IllegalArgumentException e){passed++;return;}throw new AssertionError("Unexpected skill acceptance");}
    private void rejectTrace(String value){try{FlexibleWorkflowCodec.compile(value);}catch(IllegalArgumentException e){passed++;return;}throw new AssertionError("Unexpected trace acceptance");}
    @Override public void onStart(){Bundle result=new Bundle();try{
        JSONObject skill=FlexibleWorkflowCodec.compile(raw);WorkflowCodec.decode(skill.toString());passed++;
        rejectTrace(raw+" {}");
        JSONObject bad=new JSONObject(raw);bad.put("approved",true);rejectTrace(bad.toString());
        bad=new JSONObject(raw);bad.getJSONObject("final").getJSONArray("saved").put(1,61);rejectTrace(bad.toString());
        bad=new JSONObject(raw);bad.getJSONArray("steps").getJSONObject(0).put("eventTime",true);rejectTrace(bad.toString());
        rejectSkill(new JSONObject(skill.toString()).put("approved",true).toString());
        rejectSkill(new JSONObject(skill.toString()).put("appPackage","other.app").toString());
        bad=new JSONObject(skill.toString());bad.getJSONArray("steps").getJSONObject(0).put("sourceIndex",2);rejectSkill(bad.toString());
        bad=new JSONObject(skill.toString());bad.getJSONArray("steps").getJSONObject(0).put("operation","SAVE");rejectSkill(bad.toString());
        bad=new JSONObject(skill.toString());bad.getJSONArray("finalGoals").put(1,61);rejectSkill(bad.toString());
        rejectSkill(skill.toString().replace("\"kind\":","\"kind\":\"duplicate\",\"kind\":"));
        result.putString("compiled",Base64.encodeToString(skill.toString().getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP));
        result.putString("result","PASS flexible codec checks="+passed+"; no approvals changed");finish(-1,result);
    }catch(Throwable e){result.putString("error",e.toString());finish(1,result);}}
}
