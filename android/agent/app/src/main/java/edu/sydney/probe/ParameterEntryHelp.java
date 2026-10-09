package edu.sydney.probe;
import java.util.Set;

/** Presentation only: does not grant permission, change calls or reinterpret receipts. */
final class ParameterEntryHelp {
    static String text(String raw,boolean en){
        String reason=ParameterOutcome.safeEntryReason(raw);
        String hint;
        if(Set.of("UNSUPPORTED_VALUE","VALUE_ENUM").contains(reason))
            hint=en?"This control does not support that value. Brightness: 20, 40, 60, 80 or 100; fan speed: 1, 2 or 3. Change the value and add the call again.":"当前控件不支持这个数值。亮度可选 20、40、60、80、100；风速可选 1、2、3。修改后重新添加调用。";
        else if(Set.of("PARAMETER_INTEGER","VALUE_TYPE","VALUE_RANGE","PERCENT_RANGE").contains(reason))
            hint=en?"Use a supported whole-number value. Check the control's allowed values, then add the call again.":"请填写控件支持的整数。检查允许的数值，修改后重新添加调用。";
        else if("POWER_STATE".equals(reason))hint=en?"Power accepts on or off. Change the value and add the call again.":"开关参数请填 on 或 off。修改后重新添加调用。";
        else if("SERVICE_OFF".equals(reason))hint=en?"The accessibility service is not connected. Enable Demo Probe in Android accessibility settings, then preview again.":"无障碍服务尚未连接。请在安卓无障碍设置中开启 Demo Probe，再重新预览。";
        else if(Set.of("SELECTION_DEADLINE","REMOTE_BUSY","ENTRY_UNAVAILABLE").contains(reason))
            hint=en?"The model connection did not return a usable answer; this is not a parameter error. Check the connection and try again yourself. No automatic retry.":"模型连接没有返回可用结果，这不是参数错误。请检查连接后手动再试；系统不会自动重试。";
        else if(Set.of("STALE_CONFIRMATION","SELECTION_CHANGED","PARAMETER_BINDING_CHANGED").contains(reason))
            hint=en?"The command, source or confirmation changed. Check the current selection and preview again; the old confirmation cannot run.":"指令、来源或确认条件已变化。检查当前选择后重新预览，旧确认不会执行。";
        else if("STORAGE_UNCONFIRMED".equals(reason))hint=en?"Saved evidence could not be confirmed. Check storage before selecting the skill again.":"无法确认已保存的证据。请检查存储后重新选择技能。";
        else if(Set.of("NO_PARAMETER_SOURCE","UNBOUND_DEVICE","UNBOUND_CAPABILITY","UNKNOWN_ENTITY").contains(reason))
            hint=en?"No reviewed local binding supports this device or action. Select a compatible demonstrated skill; do not assume an unseen control can run.":"没有支持该设备或动作的已审核本地绑定。请选择兼容的示范技能，未绑定的控件不会执行。";
        else hint=en?"The call could not be accepted. Check the skill and its arguments, then preview again. Technical details below can help diagnose the cause.":"调用未被接受。请检查技能和参数后重新预览；下方技术信息可用于定位原因。";
        return (en?"No formal execution started.\n":"未开始正式执行。\n")+hint;
    }
}
