package edu.sydney.probe;

import android.content.Context;
import android.os.SystemClock;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Per-run append-only evidence; failure must prevent further input. */
final class WorkflowJournal {
    private final File file;
    private final String runId;
    private int sequence;
    WorkflowJournal(Context context,String id) {
        runId=id;file=new File(context.getFilesDir(),"workflow-journal-"+id+".jsonl");
        try {if(!file.createNewFile())throw new IOException("existing run");}
        catch(IOException e){throw new IllegalStateException("JOURNAL_UNAVAILABLE",e);}
    }
    void add(String kind,int step,int phase,JSONObject data) {
        try(FileOutputStream stream=new FileOutputStream(file,true)) {
            JSONObject row=new JSONObject().put("runId",runId).put("seq",++sequence).put("ms",SystemClock.elapsedRealtime())
                .put("kind",kind).put("stepIndex",step).put("phase",phase).put("data",data);
            stream.write((row.toString()+"\n").getBytes(StandardCharsets.UTF_8));stream.getFD().sync();
        }catch(Exception e){throw new IllegalStateException("JOURNAL_UNAVAILABLE",e);}
    }
}
