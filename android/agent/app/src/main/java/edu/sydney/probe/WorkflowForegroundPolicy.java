package edu.sydney.probe;
import java.util.List;
/** Classifications only: never persist a foreign package name or window title. */
final class WorkflowForegroundPolicy {
    static String classify(List<String> focused){
        if(focused==null||focused.size()!=1)return "UNKNOWN";
        String pkg=focused.get(0);if(pkg==null||pkg.isBlank())return "UNKNOWN";
        if(pkg.equals("edu.sydney.transferlab"))return "APP";
        if(pkg.equals("edu.sydney.probe"))return "CONTROLLER";
        return "OTHER";
    }
    static boolean expired(long unknownSince,long now){return unknownSince>=0&&now-unknownSince>=2000;}
}
