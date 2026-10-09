package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import org.json.*;
import java.util.concurrent.*;

/** Runs only with the explicitly named local scripted test server; no model or GUI. */
public final class SemanticClientChecks extends Instrumentation {
    private int checks;
    private JSONArray catalog()throws Exception {
        return new JSONArray().put(new JSONObject().put("device","reading_lamp").put("name","阅读灯")
            .put("aliases",new JSONArray().put("Reading lamp"))
            .put("capabilities",new JSONArray().put(new JSONObject().put("skill","SetBrightness")
                .put("domain",new JSONObject().put("values",new JSONArray().put(20).put(80))))));
    }
    private JSONObject request(String text,boolean mutate)throws Exception {
        JSONArray source=catalog();var request=new WorkflowSelectionClient.Request(text,source,"a".repeat(48),WorkflowSelectionClient.Kind.SEMANTIC);
        if(mutate)source.getJSONObject(0).getJSONArray("capabilities").getJSONObject(0).getJSONObject("domain").put("values",new JSONArray().put(20));
        CountDownLatch ready=new CountDownLatch(1);JSONObject[] result={null};Exception[] error={null};
        request.start((data,failure)->{result[0]=data;error[0]=failure;ready.countDown();});
        if(!ready.await(10,TimeUnit.SECONDS))throw new AssertionError("Test server callback timeout");
        if(error[0]!=null)throw error[0];return result[0];
    }
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle out=new Bundle();try{
        var pending=new WorkflowSelectionClient.Request("pending",catalog(),"a".repeat(48),WorkflowSelectionClient.Kind.SEMANTIC);
        CountDownLatch pendingDone=new CountDownLatch(1);Exception[] pendingError={null};
        pending.start((data,error)->{pendingError[0]=error;pendingDone.countDown();});
        boolean busy=false;try{new WorkflowSelectionClient.Request("must_not_send",catalog(),"a".repeat(48),WorkflowSelectionClient.Kind.SEMANTIC).start((data,error)->{});}
        catch(IllegalArgumentException expected){busy=expected.getMessage().equals("REMOTE_BUSY");}
        if(!busy)throw new AssertionError("Concurrent request admitted");checks++;
        if(!pendingDone.await(10,TimeUnit.SECONDS)||pendingError[0]!=null)throw new AssertionError("Pending failed");checks++;
        for(String text:new String[]{"valid","snapshot","thirtytwo"}){
            JSONObject data=request(text,text.equals("snapshot"));
            int expected=text.equals("thirtytwo")?32:1;
            if(!data.getString("status").equals("invoke")||data.getJSONArray("calls").length()!=expected)throw new AssertionError(text);
            checks++;
        }
        for(String text:new String[]{"invalid_tail","wrong_id","illegal_noninvoke","extra","float"}){
            boolean rejected=false;try{request(text,false);}catch(IllegalArgumentException expected){rejected=true;}
            if(!rejected)throw new AssertionError("Accepted "+text);checks++;
        }
        out.putString("summary","PASS SemanticClientChecks checks="+checks+"; scripted HTTP only; GUI runs=0; model calls=0");finish(-1,out);
    }catch(Throwable error){out.putString("error",error.getClass().getSimpleName()+": "+error.getMessage());finish(1,out);}}
}
