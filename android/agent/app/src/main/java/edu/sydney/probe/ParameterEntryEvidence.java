package edu.sydney.probe;
import android.content.Context;
import android.util.AtomicFile;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Refused entry != a failed formal run. No text, parameters or credentials are recorded. */
final class ParameterEntryEvidence {
    static JSONObject record(Context context,String reason)throws Exception{
        return record(context,reason,null);
    }
    static JSONObject record(Context context,String reason,String fallbackStage)throws Exception{
        String code=ParameterOutcome.safeEntryReason(reason),entryId=UUID.randomUUID().toString();
        String stage=ParameterOutcome.stage(code,0);
        if("ENTRY_UNAVAILABLE".equals(code)&&java.util.Set.of("parsing","validation","binding","execution","verification").contains(String.valueOf(fallbackStage)))stage=fallbackStage;
        JSONObject data=new JSONObject().put("kind","PARAMETER_ENTRY_RESULT").put("entryId",entryId)
            .put("status",ParameterOutcome.entryStatus(code)).put("reason",code).put("failureStage",stage)
            .put("formalStarted",false).put("formalInputs",0).put("lastFormalRunId",ExecutionResultData.latestRunId(context));
        AtomicFile file=new AtomicFile(new File(context.getFilesDir(),"parameter-entry-"+entryId+".json"));
        FileOutputStream stream=file.startWrite();
        try{stream.write(data.toString().getBytes(StandardCharsets.UTF_8));file.finishWrite(stream);}
        catch(Exception failure){file.failWrite(stream);throw failure;}
        return data;
    }
}
