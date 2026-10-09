package edu.sydney.probe;
import java.net.*;
import java.nio.charset.StandardCharsets;
import org.json.*;
final class TeachingClient {
    static JSONObject request(String trace,String pairing) throws Exception {
        if(!pairing.matches("[a-f0-9]{48}"))throw new IllegalArgumentException("PAIRING_REQUIRED");
        String id=java.util.UUID.randomUUID().toString().replace("-","");
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8765/v1/workflows").openConnection();
        c.setConnectTimeout(4000);c.setReadTimeout(50000);c.setInstanceFollowRedirects(false);
        c.setRequestMethod("POST");c.setDoOutput(true);c.setRequestProperty("Authorization","Bearer "+pairing);
        c.setRequestProperty("Content-Type","application/json; charset=utf-8");
        try {
            byte[] data=new JSONObject().put("request_id",id).put("trace",new JSONObject(trace)).toString().getBytes(StandardCharsets.UTF_8);
            if(data.length>262144)throw new IllegalArgumentException("TRACE_TOO_LARGE");
            c.setFixedLengthStreamingMode(data.length);
            try(java.io.OutputStream out=c.getOutputStream()){out.write(data);}
            int code=c.getResponseCode();if(code!=200)throw new IllegalArgumentException("BRIDGE_HTTP_"+code);
            byte[] bytes;try(java.io.InputStream in=c.getInputStream()){bytes=in.readNBytes(FlexibleWorkflowCodec.LIMIT+1);}
            if(bytes.length>FlexibleWorkflowCodec.LIMIT)throw new IllegalArgumentException("RESPONSE_TOO_LARGE");
            JSONObject result=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
            if(result.length()!=5||!id.equals(result.getString("request_id"))||!"UNREVIEWED".equals(result.getString("reviewStatus")))throw new IllegalArgumentException("RESPONSE_MISMATCH");
            String status=result.getString("status");
            if(!java.util.List.of("candidate","clarify","reject").contains(status))throw new IllegalArgumentException("STATUS");
            if(result.getString("reason").length()>500)throw new IllegalArgumentException("REASON");
            if(status.equals("candidate")) {
                JSONObject skill=WorkflowCodec.decode(result.getJSONObject("skill").toString());
                JSONObject source=new JSONObject(trace);
                if(!source.getString("traceId").equals(skill.getString("traceId"))||!source.getString("goal").equals(skill.getString("goal")))throw new IllegalArgumentException("TRACE_MISMATCH");
            }else if(!result.isNull("skill"))throw new IllegalArgumentException("UNEXPECTED_SKILL");
            return result;
        }finally{c.disconnect();}
    }
}
