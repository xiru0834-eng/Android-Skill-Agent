package edu.sydney.probe;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.json.*;
import java.util.concurrent.*;

final class WorkflowSelectionClient {
    enum Kind {
        SELECTION("/v1/skill-selections",32768,4096),
        PARAMETERS("/v1/parameter-calls",32768,8192),
        SEMANTIC("/v2/parameter-calls",65536,SemanticParameterCodec.RESPONSE_LIMIT),
        FLOW("/v3/flow-tasks",65536,131072);
        final String path;final int requestLimit,responseLimit;
        Kind(String path,int requestLimit,int responseLimit){this.path=path;this.requestLimit=requestLimit;this.responseLimit=responseLimit;}
    }
    interface Callback {void complete(JSONObject result,Exception error);}
    private static final Object ADMISSION=new Object();
    private static Request activeRequest;
    private static final ThreadPoolExecutor WORK=new ThreadPoolExecutor(1,1,30,TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(1),r->{Thread t=new Thread(r,"workflow-selection");t.setDaemon(true);return t;});
    private static final ThreadPoolExecutor CANCEL=new ThreadPoolExecutor(1,1,30,TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(1),r->{Thread t=new Thread(r,"workflow-cancellation");t.setDaemon(true);return t;});

    static final class Request {
        private final String id=java.util.UUID.randomUUID().toString().replace("-","");
        private final String text,pairing;
        private final JSONArray catalog;
        private final Kind kind;
        private final SelectionLease lease;
        private volatile HttpURLConnection connection;
        private volatile boolean started,completed;
        Request(String text,JSONArray catalog,String pairing) throws Exception {
            this(text,catalog,pairing,false);
        }
        Request(String text,JSONArray catalog,String pairing,boolean parameters) throws Exception {
            this(text,catalog,pairing,parameters?Kind.PARAMETERS:Kind.SELECTION);
        }
        Request(String text,JSONArray catalog,String pairing,Kind kind) throws Exception {
            if(pairing==null||!pairing.matches("[a-f0-9]{48}"))throw new IllegalArgumentException("PAIRING_REQUIRED");
            if(kind==null)throw new IllegalArgumentException("REQUEST_KIND");
            this.text=kind==Kind.SEMANTIC||kind==Kind.FLOW?SemanticParameterCodec.text(text,2000):SelectionText.checked(text);
            this.catalog=new JSONArray(catalog.toString());this.pairing=pairing;this.kind=kind;
            this.lease=kind==Kind.SEMANTIC||kind==Kind.FLOW?SelectionLease.semantic(System.nanoTime()):new SelectionLease(System.nanoTime(),9000);
            if(kind==Kind.SEMANTIC)SemanticParameterCodec.catalog(this.catalog);
        }
        int deadlineMillis(){return kind==Kind.SEMANTIC||kind==Kind.FLOW?SelectionLease.SEMANTIC_MILLIS:9000;}
        synchronized void start(Callback callback){
            if(started)throw new IllegalArgumentException("REQUEST_ALREADY_STARTED");
            synchronized(ADMISSION){
                // A callback reports completion before its worker frame returns. One
                // bounded hand-off slot allows immediate reuse, not concurrent RPCs.
                if(activeRequest!=null&&!activeRequest.completed){lease.cancel();throw new IllegalArgumentException("REMOTE_BUSY");}
                started=true;
                try{WORK.execute(()->{JSONObject result=null;Exception failure=null;
                    try{result=send();}catch(Exception e){failure=e;}
                    finally{completed=true;}
                    callback.complete(result,failure);
                });activeRequest=this;}catch(RejectedExecutionException e){started=false;lease.cancel();throw new IllegalArgumentException("REMOTE_BUSY");}
            }
        }
        void cancel(){
            lease.cancel();
            if(!started||completed)return;
            try{CANCEL.execute(()->{
                // Send revocation before disconnecting the pending read. Local ticket
                // invalidation already happened and does not depend on this RPC.
                HttpURLConnection revoke=null;
                try{
                    revoke=open("/v1/skill-selection-cancellations",1500,1500,pairing);
                    byte[] data=new JSONObject().put("request_id",id).toString().getBytes(StandardCharsets.UTF_8);
                    revoke.setFixedLengthStreamingMode(data.length);
                    try(java.io.OutputStream out=revoke.getOutputStream()){out.write(data);}
                    revoke.getResponseCode();
                }catch(Exception ignored){}finally{
                    if(revoke!=null)revoke.disconnect();
                    HttpURLConnection active=connection;if(active!=null)active.disconnect();
                }
            });}catch(RejectedExecutionException ignored){/* bounded queue; local revocation is sufficient for safety */}
        }
        void assertCurrent(){lease.remainingMillis(System.nanoTime());}
        private JSONObject send() throws Exception {
            int remaining=lease.remainingMillis(System.nanoTime());
            HttpURLConnection c=open(kind.path,Math.min(4000,remaining),remaining,pairing);connection=c;
            try {
                lease.remainingMillis(System.nanoTime());
                byte[] data=new JSONObject().put("request_id",id).put("text",text).put("skills",catalog).toString().getBytes(StandardCharsets.UTF_8);
                if(data.length>kind.requestLimit)throw new IllegalArgumentException("CATALOG_TOO_LARGE");c.setFixedLengthStreamingMode(data.length);
                try(java.io.OutputStream out=c.getOutputStream()){out.write(data);}
                c.setReadTimeout(lease.remainingMillis(System.nanoTime()));
                int code=c.getResponseCode();if(code!=200){
                    String reason="BRIDGE_HTTP_"+code;
                    try(java.io.InputStream in=c.getErrorStream()){
                        if(in!=null){byte[] error=in.readNBytes(1025);
                            if(error.length<=1024){JSONObject parsed=new JSONObject(new String(error,StandardCharsets.UTF_8));
                                String named=parsed.optString("error");
                                if(java.util.List.of("SELECTION_DEADLINE","SELECTION_CANCELLED","REMOTE_BUSY").contains(named))reason=named;
                            }
                        }
                    }catch(Exception ignored){}
                    throw new IllegalArgumentException(reason);
                }
                c.setReadTimeout(lease.remainingMillis(System.nanoTime()));
                int limit=kind.responseLimit;
                byte[] bytes;try(java.io.InputStream in=c.getInputStream()){bytes=in.readNBytes(limit+1);}
                if(bytes.length>limit)throw new IllegalArgumentException("RESPONSE_TOO_LARGE");
                String raw=new String(bytes,StandardCharsets.UTF_8);
                JSONObject result;
                try{result=kind==Kind.FLOW?FlowKnowledgeStore.response(raw,id,catalog):kind==Kind.SEMANTIC?SemanticParameterCodec.response(raw,id,catalog):
                    kind==Kind.PARAMETERS?ParameterSkillCodec.validateResponse(raw,id,catalog):validate(raw,id,catalog);
                }catch(java.io.IOException|org.json.JSONException malformed){
                    // Parsing an already fully-read String cannot be a network failure.
                    // Android JsonReader also uses IOException for malformed JSON.
                    throw new IllegalArgumentException("INVALID_JSON",malformed);
                }
                lease.remainingMillis(System.nanoTime());return result;
            }finally{c.disconnect();connection=null;}
        }
    }
    private static HttpURLConnection open(String path,int connectMs,int readMs,String pairing) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8765"+path).openConnection();
        c.setConnectTimeout(connectMs);c.setReadTimeout(readMs);c.setInstanceFollowRedirects(false);
        c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+pairing);
        c.setRequestProperty("Content-Type","application/json; charset=utf-8");return c;
    }
    static JSONObject request(String text,JSONArray catalog,String pairing) throws Exception {
        return new Request(text,catalog,pairing).send();
    }
    static void validateSnapshot(String previousText,String currentText,String previousCatalog,String currentCatalog){
        if(previousText==null||previousCatalog==null||!previousText.equals(currentText)||!previousCatalog.equals(currentCatalog))
            throw new IllegalArgumentException("SELECTION_CHANGED");
    }
    static JSONObject validate(String raw,String id,JSONArray catalog) throws Exception {
        WorkflowCodec.checkJson(raw,4096);JSONObject r=new JSONObject(raw);WorkflowCodec.fields(r,"request_id","status","skill_id","message");
        WorkflowCodec.require(id.equals(r.get("request_id"))&&r.get("message") instanceof String&&r.getString("message").length()<=500,"RESPONSE_MISMATCH");
        String status=r.getString("status");WorkflowCodec.require(java.util.List.of("invoke","clarify","reject").contains(status),"STATUS");
        boolean found=false;for(int i=0;i<catalog.length();i++)if(catalog.getJSONObject(i).get("id").equals(r.opt("skill_id")))found=true;
        WorkflowCodec.require(status.equals("invoke")?found:r.isNull("skill_id"),"UNKNOWN_SELECTION");return r;
    }
}
