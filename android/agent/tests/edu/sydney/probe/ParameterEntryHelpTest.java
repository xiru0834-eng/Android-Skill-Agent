package edu.sydney.probe;

public final class ParameterEntryHelpTest {
    private static int assertions;
    private static void contains(String text,String part){assertions++;if(!text.contains(part))throw new AssertionError(text+" lacks "+part);}
    public static void main(String[] args){
        contains(ParameterEntryHelp.text("UNSUPPORTED_VALUE",false),"20、40、60、80、100");
        contains(ParameterEntryHelp.text("UNSUPPORTED_VALUE",true),"20, 40, 60, 80 or 100");
        contains(ParameterEntryHelp.text("POWER_STATE",false),"on 或 off");
        contains(ParameterEntryHelp.text("SERVICE_OFF",false),"无障碍");
        contains(ParameterEntryHelp.text("SERVICE_OFF",true),"accessibility");
        contains(ParameterEntryHelp.text("ENTRY_UNAVAILABLE",false),"不是参数错误");
        contains(ParameterEntryHelp.text("SELECTION_DEADLINE",true),"No automatic retry");
        contains(ParameterEntryHelp.text("STALE_CONFIRMATION",false),"重新预览");
        for(String reason:new String[]{"VALUE_TYPE","UNKNOWN_ENTITY","NO_PARAMETER_SOURCE","STORAGE_UNCONFIRMED","ARGUMENT_FIELDS","CAPABILITY","CALL_COUNT",null,"private detail"}){
            contains(ParameterEntryHelp.text(reason,false),"未开始正式执行");
            contains(ParameterEntryHelp.text(reason,true),"No formal execution started");
        }
        String[] safe= {"UNSUPPORTED_VALUE","PARAMETER_INTEGER","PERCENT_RANGE","POWER_STATE","UNKNOWN_ENTITY","UNBOUND_DEVICE","UNBOUND_CAPABILITY","CALL_COUNT","ARGUMENT_FIELDS","UNKNOWN_SKILL","VALUE_TYPE","VALUE_RANGE","VALUE_ENUM","DEVICE_TYPE","RESPONSE_MISMATCH","UNEXPECTED_CALLS","STATUS","PARAMETER_BINDING_CHANGED","NO_PARAMETER_SOURCE","STORAGE_UNCONFIRMED","STALE_CONFIRMATION","SELECTION_CHANGED","SELECTION_DEADLINE","REMOTE_BUSY","SERVICE_OFF","CAPABILITY","ENTRY_INVALID","ENTRY_UNAVAILABLE","MODEL_REJECTED","CLARIFICATION_REQUIRED"};
        for(String code:safe)for(boolean en:new boolean[]{false,true}){
            String text=ParameterEntryHelp.text(code,en);assertions++;if(text.isBlank()||text.contains("private detail"))throw new AssertionError(code);
        }
        System.out.println("ParameterEntryHelpTest PASS "+assertions+" assertions");
    }
}
