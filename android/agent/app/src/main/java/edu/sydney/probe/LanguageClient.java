package edu.sydney.probe;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

/** Only USB-forwarded loopback; never stores or transports an OpenAI key. */
public final class LanguageClient {
    public static LanguageDecision request(String id,String text,String pairing) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:8765/v1/intents").openConnection();
        c.setConnectTimeout(4000);c.setReadTimeout(50000);c.setInstanceFollowRedirects(false);
        c.setRequestMethod("POST");c.setDoOutput(true);
        c.setRequestProperty("Authorization","Bearer "+pairing);
        c.setRequestProperty("Content-Type","application/json; charset=utf-8");
        try {
            byte[] data=new JSONObject().put("request_id",id).put("text",text).toString().getBytes(StandardCharsets.UTF_8);
            c.setFixedLengthStreamingMode(data.length);
            try(java.io.OutputStream out=c.getOutputStream()) { out.write(data); }
            int code=c.getResponseCode();
            if(code!=200) throw new IllegalArgumentException("BRIDGE_HTTP_"+code);
            byte[] response;
            try(java.io.InputStream in=c.getInputStream()) { response=in.readNBytes(8193); }
            if(response.length>8192) throw new IllegalArgumentException("RESPONSE_TOO_LARGE");
            JSONObject o=new JSONObject(new String(response,StandardCharsets.UTF_8));
            if(o.length()!=6 || !id.equals(o.getString("request_id"))) throw new IllegalArgumentException("REQUEST_MISMATCH");
            return new LanguageDecision(o.getString("status"),o.getString("skill_id"),bool(o,"lamp"),bool(o,"fan"),o.getString("message"));
        } finally { c.disconnect(); }
    }
    private static Boolean bool(JSONObject o,String key) throws Exception {
        Object value=o.get(key);if(value==JSONObject.NULL) return null;
        if(!(value instanceof Boolean)) throw new IllegalArgumentException("INVALID_BOOLEAN");
        return (Boolean)value;
    }
}
