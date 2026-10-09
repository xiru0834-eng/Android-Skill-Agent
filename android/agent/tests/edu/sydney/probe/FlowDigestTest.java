package edu.sydney.probe;
public final class FlowDigestTest {
    private static void equal(String a,String b){if(!a.equals(b))throw new AssertionError(a+" != "+b);}
    public static void main(String[] args){
        equal("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",FlowDigest.sha256(""));
        equal("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",FlowDigest.sha256("abc"));
        for(String value:java.util.List.of("卧室灯亮度80%","a".repeat(131072),"\u0000\n\r\t","🌙")){
            try{StringBuilder ref=new StringBuilder();for(byte b:java.security.MessageDigest.getInstance("SHA-256").digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)))ref.append(String.format(java.util.Locale.ROOT,"%02x",b&255));equal(ref.toString(),FlowDigest.sha256(value));}
            catch(Exception error){throw new AssertionError(error);}
        }
        if(FlowDigest.sha256("approved").equals(FlowDigest.sha256("changed")))throw new AssertionError("mutation lost");
        System.out.println("PASS FlowDigestTest: UTF-8/hash identity and changed bytes");
    }
}
