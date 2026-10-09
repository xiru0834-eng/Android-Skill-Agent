package edu.sydney.probe;

import java.util.Locale;

/** Presentation rules only. Never promotes partial progress to verified success. */
final class ExecutionResultPolicy {
    enum Destination { RECORDING_REVIEW, EXECUTION_RESULT }
    private ExecutionResultPolicy(){}
    static Destination destination(boolean recording){return recording?Destination.RECORDING_REVIEW:Destination.EXECUTION_RESULT;}
    static boolean validRunId(String id){return id!=null&&id.matches("(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}");}
    static boolean matches(String actual,String expected){return validRunId(actual)&&actual.equals(expected);}
    static boolean verified(String status,String actual,String expected){return "SUCCEEDED".equals(status)&&matches(actual,expected);}
    static boolean shouldCelebrate(String status,String actual,String expected,String seen,boolean animations){
        return animations&&verified(status,actual,expected)&&!actual.equals(seen);
    }
    static long durationMs(long start,long end){return start<0||end<start?-1:end-start;}
    static String duration(long ms,boolean en){return ms<0?(en?"Not available":"暂无数据"):String.format(Locale.ROOT,"%.1f",ms/1000.0)+(en?" s":" 秒");}
    static String title(String status,boolean matching,boolean en){
        if(!matching)return en?"No matching execution result":"暂无对应执行结果";
        return switch(status==null?"":status){
            case "SUCCEEDED" -> en?"Completed · targets verified":"执行完成 · 目标已核验";
            case "RUNNING" -> en?"Execution in progress":"正在执行";
            case "CANCELLED" -> en?"Stopped":"已停止";
            default -> en?"Completion not confirmed":"未确认完成";
        };
    }
}
