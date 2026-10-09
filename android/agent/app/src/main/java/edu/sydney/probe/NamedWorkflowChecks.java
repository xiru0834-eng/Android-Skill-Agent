package edu.sydney.probe;
import android.app.Instrumentation;
import android.os.Bundle;
import android.util.Base64;
import org.json.*;

/** Pure codec checks on Android; does not read or write any approval store. */
public final class NamedWorkflowChecks extends Instrumentation {
    String raw;int checks;
    interface Check {void run() throws Exception;}
    void bad(Check test) throws Exception {try{test.run();throw new AssertionError("invalid accepted");}catch(IllegalArgumentException e){checks++;}}
    void ok(boolean yes){if(!yes)throw new AssertionError();checks++;}
    @Override public void onCreate(Bundle args){super.onCreate(args);raw=new String(Base64.decode(args.getString("skill"),Base64.DEFAULT),java.nio.charset.StandardCharsets.UTF_8);start();}
    @Override public void onStart(){Bundle out=new Bundle();try{
        var entry=NamedWorkflowCodec.entry("阅读60",raw);String pack=NamedWorkflowCodec.encode(entry);
        var decoded=NamedWorkflowCodec.decode(pack);ok(entry.raw.equals(decoded.raw)&&entry.id.equals(decoded.id));
        bad(()->NamedWorkflowCodec.decode(new JSONObject(pack).put("approved",true).toString()));
        bad(()->NamedWorkflowCodec.decode(pack.replace("\"name\":","\"name\":\"x\",\"name\":")));
        bad(()->NamedWorkflowCodec.decode(pack+" {}"));
        bad(()->NamedWorkflowCodec.decode(new JSONObject(pack).put("name",false).toString()));
        bad(()->NamedWorkflowCodec.decode(new JSONObject(pack).put("version",2).toString()));
        JSONArray cat=new JSONArray().put(new JSONObject().put("id",entry.id));
        JSONObject valid=new JSONObject().put("request_id","a").put("status","invoke").put("skill_id",entry.id).put("message","review");
        ok(WorkflowSelectionClient.validate(valid.toString(),"a",cat).getString("skill_id").equals(entry.id));
        bad(()->WorkflowSelectionClient.validate(valid.toString(),"b",cat));
        bad(()->WorkflowSelectionClient.validate(new JSONObject(valid.toString()).put("skill_id","unknown").toString(),"a",cat));
        bad(()->WorkflowSelectionClient.validate(new JSONObject(valid.toString()).put("status","reject").toString(),"a",cat));
        bad(()->WorkflowSelectionClient.validate(new JSONObject(valid.toString()).put("actions",new JSONArray()).toString(),"a",cat));
        JSONObject full=WorkflowCodec.decode(raw);
        String group=full.getJSONArray("steps").getJSONObject(0).getString("id").equals("wfOpenLamp")?"Lamp":"Fan";
        int untouched=group.equals("Lamp")?2:0;
        JSONObject one=new JSONObject(raw).put("version",2);JSONArray steps=new JSONArray();
        for(int i=0;i<4;i++)steps.put(full.getJSONArray("steps").getJSONObject(i));one.put("steps",steps);
        one.getJSONArray("finalGoals").put(untouched,JSONObject.NULL).put(untouched+1,JSONObject.NULL);
        ok(WorkflowCodec.decode(one.toString()).getJSONArray("steps").length()==4);
        ok(TeachingGuide.render(one.toString(),true).contains("keep execution-start"));
        ok(TeachingGuide.render(one.toString(),false).contains("保持执行开始时"));
        ok(NamedWorkflowCodec.decode(NamedWorkflowCodec.encode(NamedWorkflowCodec.entry("Single",one.toString()))).raw.equals(one.toString()));
        bad(()->WorkflowCodec.decode(new JSONObject(one.toString()).put("version",1).toString()));
        JSONObject half=new JSONObject(one.toString());half.getJSONArray("finalGoals").put(untouched,0);
        bad(()->WorkflowCodec.decode(half.toString()));
        bad(()->WorkflowCodec.decode(new JSONObject(one.toString()).put("finalGoals",full.getJSONArray("finalGoals")).toString()));
        JSONObject wrongRoute=new JSONObject(one.toString());wrongRoute.getJSONArray("steps").getJSONObject(0).put("id",group.equals("Lamp")?"wfOpenFan":"wfOpenLamp");
        bad(()->WorkflowCodec.decode(wrongRoute.toString()));
        out.putString("result","PASS checks="+checks+"; no approvals modified");finish(-1,out);
    }catch(Throwable e){out.putString("error",e.toString());finish(1,out);}}
}
