package edu.sydney.probe;

import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.widget.TextView;
import org.json.*;
import java.util.*;

/** Isolated adapter checks. Optional display fixtures are labelled, never task evidence. */
public final class ExecutionResultChecks extends Instrumentation {
    private Bundle args;
    private int checks;
    private String displayFiles="";
    private void check(boolean value,String name){if(!value)throw new AssertionError(name);checks++;}
    @Override public void onCreate(Bundle arguments){super.onCreate(arguments);args=arguments==null?new Bundle():arguments;start();}
    private JSONObject sample(String run,String status)throws Exception{
        return new JSONObject().put("runId",run).put("status",status).put("reason",status.equals("SUCCEEDED")?"ALL_TARGETS_VERIFIED":"TASK_TIMEOUT")
            .put("startedMs",1000).put("finishedMs",3000).put("deadlineMs",5000).put("completedSteps",4).put("observations",8)
            .put("actions",new JSONArray().put(new JSONObject().put("id","diagnostic")))
            .put("traceSha256","diagnostic-presentation-only").put("requestedGoals",new JSONArray("[1,60,null,null]"));
    }
    private void displaySnapshot(Activity screen,String run,String suffix)throws Exception{
        android.graphics.Bitmap image=getUiAutomation(android.app.UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES).takeScreenshot();
        if(image==null)throw new AssertionError("display screenshot missing");
        String name="diagnostic-result-"+run+"-"+suffix+".png";
        try(var stream=new java.io.FileOutputStream(new java.io.File(getTargetContext().getFilesDir(),name))){image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,stream);}
        image.recycle();displayFiles+=(displayFiles.isEmpty()?"":",")+name;
    }
    @Override public void onStart(){
        Bundle output=new Bundle();Context actual=getTargetContext();String space="result_diagnostic_"+UUID.randomUUID().toString().replace("-","");
        Context isolated=new ContextWrapper(actual){@Override public SharedPreferences getSharedPreferences(String name,int mode){return actual.getSharedPreferences(space,mode);}};
        java.io.File fixture=null;
        try{
            if("true".equals(args.getString("display","false"))){
                String run=UUID.randomUUID().toString(),state=args.getString("state","SUCCEEDED");
                JSONObject value=sample(run,state);if(state.equals("CANCELLED"))value.put("reason","USER_OR_SERVICE_STOP");
                fixture=new java.io.File(actual.getFilesDir(),"workflow-result-"+run+".json");
                try(var stream=new java.io.FileOutputStream(fixture)){stream.write(value.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                Activity screen=startActivitySync(ExecutionResultActivity.intent(actual,run).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                waitForIdleSync();
                check(screen instanceof ExecutionResultActivity,"result destination");
                String storedResult=new WorkflowStore(actual).result();
                runOnMainSync(()->{
                    check(screen.findViewById(actual.getResources().getIdentifier("teachName","id",actual.getPackageName()))==null,"recording form leaked into result");
                    TextView heading=screen.findViewById(actual.getResources().getIdentifier("executionStatus","id",actual.getPackageName()));
                    check(heading!=null,"result heading missing");
                    boolean success=heading.getText().toString().contains("目标已核验")||heading.getText().toString().contains("targets verified");
                    check(success==state.equals("SUCCEEDED"),"wrong success label");
                });
                displaySnapshot(screen,run,"first");
                runOnMainSync(()->screen.findViewById(actual.getResources().getIdentifier("executionLanguage","id",actual.getPackageName())).performClick());
                waitForIdleSync();displaySnapshot(screen,run,"language");
                check(new WorkflowStore(actual).result().equals(storedResult),"view/language wrote task result");
                runOnMainSync(()->screen.findViewById(actual.getResources().getIdentifier("executionLanguage","id",actual.getPackageName())).performClick());
                waitForIdleSync();
                output.putString("result","PASS display fixture only; not a real executed task; checks="+checks);output.putString("runId",run);output.putString("screenshots",displayFiles);
            }else{
                String run=UUID.randomUUID().toString();JSONObject good=sample(run,"SUCCEEDED");
                ExecutionResultData data=ExecutionResultData.parse(good.toString(),run);
                check(data!=null&&data.valid&&data.inputs==1&&data.elapsedMs==2000,"valid adapter");
                check(!ExecutionResultData.parse(good.toString(),UUID.randomUUID().toString()).valid,"stale success accepted");
                check(ExecutionResultData.parse("broken",run)==null,"malformed JSON accepted");
                check(ExecutionResultData.parse("{}",run)==null,"missing fields accepted");
                check(ExecutionResultData.parse("x".repeat(524289),run)==null,"oversized result accepted");
                for(String field:new String[]{"runId","status","reason","startedMs","finishedMs","completedSteps","observations","actions"}){
                    JSONObject missing=new JSONObject(good.toString());missing.remove(field);check(ExecutionResultData.parse(missing.toString(),run)==null,"missing "+field);
                }
                check(!ExecutionResultData.parse(new JSONObject(good.toString()).put("finishedMs",999).toString(),run).valid,"negative duration accepted");
                check(!ExecutionResultData.parse(new JSONObject(good.toString()).put("completedSteps",-1).toString(),run).valid,"negative steps accepted");
                check(!ExecutionResultData.parse(new JSONObject(good.toString()).put("observations",-1).toString(),run).valid,"negative observations accepted");
                check(!ExecutionResultData.parse(new JSONObject(good.toString()).put("deadlineMs",3000).toString(),run).valid,"late success accepted");
                check(!ExecutionResultData.parse(new JSONObject(good.toString()).put("status","UNKNOWN").toString(),run).valid,"unknown status accepted");
                SharedPreferences prefs=isolated.getSharedPreferences("recorded_workflows",0);prefs.edit().putString("result",good.toString()).commit();
                Map<String,?> before=new HashMap<>(prefs.getAll());
                check(ExecutionResultData.read(isolated,run).valid,"read current result");
                check(before.equals(prefs.getAll()),"read changed results or approvals");
                boolean animations=SuccessFireworksView.animationsEnabled();
                check(ExecutionCelebration.claim(isolated,data,run)==animations,"first receipt");
                check(!ExecutionCelebration.claim(isolated,data,run),"repeat celebration");
                for(String state:new String[]{"RUNNING","CANCELLED","UNCONFIRMED"}){
                    ExecutionResultData other=ExecutionResultData.parse(sample(UUID.randomUUID().toString(),state).toString(),run);
                    check(!ExecutionCelebration.claim(isolated,other,run),"wrong task or non-success "+state);
                }
                check(new WorkflowStore(isolated).result().equals(good.toString()),"feedback changed task result");
                runOnMainSync(()->{
                    SuccessFireworksView effect=new SuccessFireworksView(actual);
                    check(!effect.isClickable()&&!effect.isFocusable(),"effect captures controls");
                    check(effect.getImportantForAccessibility()==android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO,"effect pollutes accessibility");
                    effect.play();check(effect.playing()==SuccessFireworksView.animationsEnabled(),"effect ignores system animation setting");
                    effect.stop();check(!effect.playing(),"effect survives stop");
                });
                output.putString("result","PASS ExecutionResultChecks checks="+checks+"; isolated preferences; no task execution");
            }
            finish(-1,output);
        }catch(Throwable error){output.putString("error",error.toString());finish(1,output);}
        finally{actual.deleteSharedPreferences(space);if(fixture!=null)fixture.delete();}
    }
}
