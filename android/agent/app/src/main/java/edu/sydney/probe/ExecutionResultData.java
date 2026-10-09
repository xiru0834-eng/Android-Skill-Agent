package edu.sydney.probe;

import android.content.Context;
import org.json.*;
import java.nio.charset.StandardCharsets;

/** Read-only, run-bound adapter. No approval, recording or execution writes. */
final class ExecutionResultData {
    final JSONObject raw;
    final boolean valid;
    final String runId,status,reason,traceSha256;
    final long elapsedMs;
    final int completedSteps,inputs,observations;
    private ExecutionResultData(JSONObject value,String expected) throws JSONException {
        raw=value;runId=value.getString("runId");status=value.getString("status");reason=value.getString("reason");
        traceSha256=value.optString("traceSha256");
        long start=value.getLong("startedMs"),end=value.getLong("finishedMs");
        elapsedMs=ExecutionResultPolicy.durationMs(start,end);
        completedSteps=value.getInt("completedSteps");observations=value.getInt("observations");inputs=value.getJSONArray("actions").length();
        boolean known=status.equals("SUCCEEDED")||status.equals("RUNNING")||status.equals("CANCELLED")||status.equals("UNCONFIRMED");
        boolean timely=!status.equals("SUCCEEDED")||(value.has("deadlineMs")&&end<value.getLong("deadlineMs"));
        valid=known&&timely&&elapsedMs>=0&&completedSteps>=0&&observations>=0&&ExecutionResultPolicy.matches(runId,expected);
    }
    static ExecutionResultData parse(String text,String expected){
        try{return text==null||text.length()>524288?null:new ExecutionResultData(new JSONObject(text),expected);}catch(Exception e){return null;}
    }
    static String latestRunId(Context context){
        try{String id=new JSONObject(new WorkflowStore(context).result()).optString("runId");return ExecutionResultPolicy.validRunId(id)?id:"";}catch(Exception e){return "";}
    }
    static ExecutionResultData read(Context context,String expected){
        if(!ExecutionResultPolicy.validRunId(expected))return null;
        ExecutionResultData current=parse(new WorkflowStore(context).result(),expected);
        if(current!=null&&current.valid)return current;
        // Only an immutable UUID-derived file in this app's own directory is eligible.
        try{var file=new java.io.File(context.getFilesDir(),"workflow-result-"+expected+".json");
            if(!file.isFile()||file.length()>524288)return current;
            try(var input=new java.io.FileInputStream(file);var bytes=new java.io.ByteArrayOutputStream()){
                byte[] buffer=new byte[4096];int length;
                while((length=input.read(buffer))!=-1){if(bytes.size()+length>524288)return null;bytes.write(buffer,0,length);}
                return parse(bytes.toString(StandardCharsets.UTF_8.name()),expected);
            }
        }catch(Exception e){return current;}
    }
}
