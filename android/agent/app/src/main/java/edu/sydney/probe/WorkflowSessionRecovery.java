package edu.sydney.probe;

import android.content.Context;
import android.os.SystemClock;
import android.util.AtomicFile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import org.json.JSONObject;

/** Seals persisted orphan sessions, preserving the checkpoint and append-only journal. */
final class WorkflowSessionRecovery {
    private static final int LIMIT=262144;
    private final Context context;
    private WorkflowSessionRecovery(Context context){this.context=context;}
    static void recover(Context context)throws Exception {
        WorkflowSessionRecovery recovery=new WorkflowSessionRecovery(context);
        recovery.execution();recovery.recording();
    }
    private void execution()throws Exception {
        String raw=new WorkflowStore(context).result();
        if(!raw.startsWith("{"))return; // The existing Not run placeholder is not a checkpoint.
        JSONObject checkpoint=new JSONObject(raw);
        if(!WorkflowInterruptionPolicy.execution(checkpoint.optString("status"),false))return;
        String id=identity(checkpoint,"runId"),original="workflow-recovery-run-"+id+"-original.json";
        byte[] bytes=raw.getBytes(StandardCharsets.UTF_8);archive(original,bytes);
        JSONObject evidence=evidence(original,bytes);
        checkpoint.put("status","UNCONFIRMED").put("reason","SERVICE_RECONNECTED").put("recovery",evidence);
        // Counts and started/finished timestamps remain those of the last persisted checkpoint.
        // Last in-flight operations may not have been persisted; do not invent an accurate final duration.
        write("workflow-recovery-run-"+id+".json",evidence);
        write("workflow-result-"+id+".json",checkpoint);write("recorded-workflow-result.json",checkpoint);
        if(!context.getSharedPreferences("recorded_workflows",0).edit().putString("result",checkpoint.toString()).commit())
            throw new IOException("RECOVERY_STORE_FAILED");
    }
    private void recording()throws Exception {
        File file=new File(context.getFilesDir(),"workflow-trace.json");if(!file.exists())return;
        byte[] bytes=read(file);JSONObject checkpoint=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        if(!WorkflowInterruptionPolicy.recording(checkpoint.optString("end"),false))return;
        if(!"WORKFLOW_TRACE".equals(checkpoint.optString("kind")))throw new IOException("RECOVERY_TRACE_KIND");
        String id=identity(checkpoint,"traceId"),original="workflow-recovery-trace-"+id+"-original.json";
        archive(original,bytes);JSONObject evidence=evidence(original,bytes);
        checkpoint.put("end","INTERRUPTED");
        if(checkpoint.optString("error").isEmpty())checkpoint.put("error","PROCESS_RESTARTED");
        write("workflow-recovery-trace-"+id+".json",evidence);
        write("workflow-trace-"+id+".json",checkpoint);write("workflow-trace.json",checkpoint);
        // The original recording audit stays unchanged, just like the execution journal.
    }
    private JSONObject evidence(String original,byte[] bytes)throws Exception {
        StringBuilder hash=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))hash.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return new JSONObject().put("kind","WORKFLOW_SESSION_RECOVERY").put("scope","LAST_PERSISTED_CHECKPOINT_ONLY")
            .put("originalFile",original).put("originalSha256",hash.toString()).put("recoveredAtMs",SystemClock.elapsedRealtime())
            .put("noAutomaticResume",true).put("timingScope","Recovery time may belong to a different boot; original times are checkpoint times");
    }
    private String identity(JSONObject value,String key)throws Exception {
        String id=value.getString(key);if(!WorkflowInterruptionPolicy.validId(id))throw new IOException("RECOVERY_ID");return id;
    }
    private byte[] read(File file)throws IOException {
        try(InputStream in=new AtomicFile(file).openRead();ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] block=new byte[4096];int count;
            while((count=in.read(block))!=-1){if(out.size()+count>LIMIT)throw new IOException("RECOVERY_SIZE");out.write(block,0,count);}
            return out.toByteArray();
        }
    }
    private void archive(String name,byte[] bytes)throws IOException {
        File file=new File(context.getFilesDir(),name);
        if(file.exists()){if(!Arrays.equals(read(file),bytes))throw new IOException("RECOVERY_CONFLICT");return;}
        writeBytes(name,bytes);
    }
    private void write(String name,JSONObject value)throws IOException {writeBytes(name,value.toString().getBytes(StandardCharsets.UTF_8));}
    private void writeBytes(String name,byte[] bytes)throws IOException {
        if(bytes.length>LIMIT)throw new IOException("RECOVERY_SIZE");
        AtomicFile file=new AtomicFile(new File(context.getFilesDir(),name));FileOutputStream stream=file.startWrite();
        try{stream.write(bytes);file.finishWrite(stream);}catch(IOException error){file.failWrite(stream);throw error;}
    }
}
