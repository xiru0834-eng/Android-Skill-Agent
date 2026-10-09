package edu.sydney.probe;
import org.json.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

/** Same existing paired loopback bridge. No API secret, redirects, retry or execution. */
final class UserLearningClient {
    private static final java.util.concurrent.ThreadPoolExecutor WORK=new java.util.concurrent.ThreadPoolExecutor(2,2,30,java.util.concurrent.TimeUnit.SECONDS,
        new java.util.concurrent.ArrayBlockingQueue<>(2),r->{Thread t=new Thread(r,"user-learning-rpc");t.setDaemon(true);return t;});
    interface Callback{void complete(JSONObject result,Exception error);}
    private volatile HttpURLConnection connection;private volatile boolean cancelled;
    private boolean started;
    void cancel(){cancelled=true;var c=connection;if(c!=null)c.disconnect();}
    synchronized void start(String id,String operation,JSONObject payload,String pairing,Callback callback){
        if(started){callback.complete(null,new IllegalStateException("REQUEST_ALREADY_STARTED"));return;}started=true;
        try{WORK.execute(()->{
            JSONObject result=null;Exception failure=null;
            try{
                if(id==null||!id.matches("[a-f0-9]{32}"))throw new IllegalArgumentException("REQUEST_ID");
                if(pairing==null||!pairing.matches("[a-f0-9]{48}"))throw new IllegalArgumentException("PAIRING_REQUIRED");
                long deadline=SystemClockCompat.now()+125000;
                if(cancelled)throw new IllegalStateException("CANCELLED");
                HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8766/v3/learning").openConnection();connection=c;
                c.setInstanceFollowRedirects(false);c.setConnectTimeout(4000);c.setReadTimeout(120000);
                c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+pairing);c.setRequestProperty("Content-Type","application/json; charset=utf-8");
                byte[] raw=new JSONObject().put("request_id",id).put("operation",operation).put("payload",payload).toString().getBytes(StandardCharsets.UTF_8);
                if(raw.length>1048576)throw new IllegalArgumentException("MATERIAL_SIZE_LIMIT");c.setFixedLengthStreamingMode(raw.length);
                try(var out=c.getOutputStream()){if(cancelled)throw new IllegalStateException("CANCELLED");out.write(raw);}
                int code=c.getResponseCode();String response;
                try(var in=code==200?c.getInputStream():c.getErrorStream()){
                    if(in==null)throw new IllegalStateException("BRIDGE_HTTP_"+code);
                    response=UserLearningFiles.read(in,1048576,()->{
                        long remaining=deadline-SystemClockCompat.now();
                        if(cancelled||remaining<=0)throw new java.io.IOException("CANCELLED_OR_LATE");
                        c.setReadTimeout((int)Math.min(remaining,120000));
                    });
                }
                var reply=new JSONObject(response);
                if(code!=200)throw new IllegalStateException(reply.optString("error","BRIDGE_HTTP_"+code));
                if(cancelled||SystemClockCompat.now()>deadline)throw new IllegalStateException("CANCELLED_OR_LATE");
                if(!id.equals(reply.getString("request_id"))||!Boolean.FALSE.equals(reply.get("execution_authority")))throw new IllegalStateException("LEARNING_RESPONSE_MISMATCH");
                result=reply.getJSONObject("result");
            }catch(Exception e){failure=e;}finally{var c=connection;connection=null;if(c!=null)c.disconnect();}
            callback.complete(result,failure);
        });}catch(java.util.concurrent.RejectedExecutionException e){callback.complete(null,new IllegalStateException("LEARNING_CLIENT_BUSY"));}
    }
    private static final class SystemClockCompat{static long now(){return android.os.SystemClock.elapsedRealtime();}}
}
