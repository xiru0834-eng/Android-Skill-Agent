package edu.sydney.probe;

/** Entry failures describe availability or invalid input, never successful execution. */
final class PortableEntryPolicy {
    private PortableEntryPolicy(){}
    static String display(Exception error){
        if(error instanceof java.net.SocketTimeoutException)return "UNCONFIRMED / SELECTION_DEADLINE";
        if(error instanceof java.io.IOException)return "UNCONFIRMED / TRANSPORT_ERROR";
        String code=error==null?null:error.getMessage();
        boolean named=code!=null&&code.matches("[A-Z][A-Z0-9_]{0,79}");
        if(named&&code.equals("SERVICE_OFF"))return "ENVIRONMENT_ERROR / "+code;
        if(named&&(java.util.List.of("SELECTION_DEADLINE","SELECTION_CANCELLED","REMOTE_BUSY","EXPORT_STORAGE").contains(code)
            ||code.equals("BRIDGE_HTTP_429")||code.matches("BRIDGE_HTTP_5[0-9]{2}")))return "UNCONFIRMED / "+code;
        if(error!=null&&error.getClass().getName().equals("org.json.JSONException"))return "REJECTED / INVALID_JSON";
        if(error instanceof IllegalArgumentException)return "REJECTED / "+(named?code:"INVALID_INPUT");
        if(error instanceof IllegalStateException&&named&&java.util.List.of("STALE_REQUEST","STALE_CONFIRMATION").contains(code))return "REJECTED / "+code;
        return "UNCONFIRMED / INTERNAL_ERROR";
    }
}
