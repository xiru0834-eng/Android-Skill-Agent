package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import android.util.Base64;
import org.json.*;

/** Contract checks only, no production approvals and no GUI execution. */
public final class WorkflowChecks extends Instrumentation {
    private String raw;
    private int passed;
    @Override public void onCreate(Bundle args){super.onCreate(args);raw=new String(Base64.decode(args.getString("skill"),Base64.DEFAULT),java.nio.charset.StandardCharsets.UTF_8);start();}
    private void rejects(String s){try{WorkflowCodec.decode(s);}catch(IllegalArgumentException e){passed++;return;}throw new AssertionError("Unexpected acceptance");}
    @Override public void onStart() {
        Bundle result=new Bundle();
        try {
            JSONObject valid=WorkflowCodec.decode(raw);passed++;
            rejects(raw.replace("\"kind\":","\"kind\":\"DUPLICATE\",\"kind\":"));
            rejects(new JSONObject(valid.toString()).put("approved",true).toString());
            rejects(new JSONObject(valid.toString()).put("appPackage","other.app").toString());
            JSONObject bad=new JSONObject(valid.toString());bad.getJSONArray("steps").getJSONObject(0).put("id","wfReset");rejects(bad.toString());
            bad=new JSONObject(valid.toString());bad.getJSONArray("steps").getJSONObject(1).put("desired",false);rejects(bad.toString());
            bad=new JSONObject(valid.toString());bad.getJSONArray("finalGoals").put(1,61);rejects(bad.toString());
            bad=new JSONObject(valid.toString());bad.getJSONArray("steps").getJSONObject(2).put("sourceIndex",1);rejects(bad.toString());
            rejects(raw+" {}");
            result.putString("result","PASS workflow codec checks="+passed+"; no approvals changed");finish(-1,result);
        }catch(Throwable e){result.putString("error",e.toString());finish(1,result);}
    }
}
