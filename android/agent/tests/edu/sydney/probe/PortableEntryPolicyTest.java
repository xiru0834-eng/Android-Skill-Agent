package edu.sydney.probe;
import java.io.IOException;
import java.net.SocketTimeoutException;

public final class PortableEntryPolicyTest {
    private static int checks;
    private static void check(Exception e,String expected){
        String actual=PortableEntryPolicy.display(e);checks++;
        if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);
    }
    public static void main(String[] args){
        for(String code:new String[]{"BRIDGE_HTTP_429","BRIDGE_HTTP_500","BRIDGE_HTTP_503","BRIDGE_HTTP_504","SELECTION_DEADLINE","SELECTION_CANCELLED","REMOTE_BUSY","SERVICE_OFF","EXPORT_STORAGE"})
            check(new IllegalArgumentException(code),(code.equals("SERVICE_OFF")?"ENVIRONMENT_ERROR":"UNCONFIRMED")+" / "+code);
        for(String code:new String[]{"PARAMETER_RANGE","STALE_REQUEST","PAIRING_REQUIRED","RESPONSE_MISMATCH","BRIDGE_HTTP_401","BRIDGE_HTTP_403","BRIDGE_HTTP_400"})
            check(new IllegalArgumentException(code),"REJECTED / "+code);
        check(new SocketTimeoutException("secret URL"),"UNCONFIRMED / SELECTION_DEADLINE");
        check(new IOException("Bearer secret-token"),"UNCONFIRMED / TRANSPORT_ERROR");
        check(new IllegalStateException("SERVICE_OFF"),"ENVIRONMENT_ERROR / SERVICE_OFF");
        check(new IllegalStateException("STALE_CONFIRMATION"),"REJECTED / STALE_CONFIRMATION");
        check(new IllegalArgumentException("LOCAL_REVIEW_REQUIRED"),"REJECTED / LOCAL_REVIEW_REQUIRED");
        check(new NullPointerException("secret-token"),"UNCONFIRMED / INTERNAL_ERROR");
        check(new Exception("https://private.invalid/key"),"UNCONFIRMED / INTERNAL_ERROR");
        check(new IllegalArgumentException("secret-token"),"REJECTED / INVALID_INPUT");
        check(new IllegalArgumentException("X".repeat(200)),"REJECTED / INVALID_INPUT");
        check(null,"UNCONFIRMED / INTERNAL_ERROR");
        System.out.println("PortableEntryPolicyTest passed: "+checks+" checks");
    }
}
