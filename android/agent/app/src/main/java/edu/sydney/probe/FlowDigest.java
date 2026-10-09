package edu.sydney.probe;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Same SHA-256 bytes/UTF-8 contract, without 32 Formatter allocations per live guard. */
final class FlowDigest {
    private static final char[] HEX="0123456789abcdef".toCharArray();
    static String sha256(String raw){
        try{
            byte[] bytes=MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));
            char[] hex=new char[bytes.length*2];
            for(int i=0;i<bytes.length;i++){int b=bytes[i]&255;hex[i*2]=HEX[b>>>4];hex[i*2+1]=HEX[b&15];}
            return new String(hex);
        }catch(java.security.NoSuchAlgorithmException unavailable){throw new IllegalStateException("SHA256_UNAVAILABLE",unavailable);}
    }
}
