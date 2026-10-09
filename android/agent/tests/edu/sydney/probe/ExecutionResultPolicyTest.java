package edu.sydney.probe;

public final class ExecutionResultPolicyTest {
    private static int checks;
    private static final String RUN="d5fc329a-1c1b-4b05-a3b6-f4b21b5e8280";
    private static final String OTHER="26e741b8-dbab-43d4-b932-5b4965a2fa89";
    public static void main(String[] args) {
        check(ExecutionResultPolicy.destination(true)==ExecutionResultPolicy.Destination.RECORDING_REVIEW);
        check(ExecutionResultPolicy.destination(false)==ExecutionResultPolicy.Destination.EXECUTION_RESULT);
        check(ExecutionResultPolicy.verified("SUCCEEDED",RUN,RUN));
        for(String state:new String[]{"RUNNING","CANCELLED","UNCONFIRMED","FAILED","succeeded","",null})
            check(!ExecutionResultPolicy.verified(state,RUN,RUN));
        for(String id:new String[]{"",null,"bad","1-1-1-1-1",OTHER})
            check(!ExecutionResultPolicy.verified("SUCCEEDED",id,RUN));
        check(!ExecutionResultPolicy.verified("SUCCEEDED",RUN,null));
        check(!ExecutionResultPolicy.verified("SUCCEEDED",RUN,""));
        check(ExecutionResultPolicy.durationMs(100,2100)==2000);
        check(ExecutionResultPolicy.durationMs(100,100)==0);
        check(ExecutionResultPolicy.durationMs(-1,100)==-1);
        check(ExecutionResultPolicy.durationMs(100,99)==-1);
        check(ExecutionResultPolicy.durationMs(Long.MAX_VALUE-1,Long.MAX_VALUE)==1);
        check(ExecutionResultPolicy.duration(2000,false).equals("2.0 秒"));
        check(ExecutionResultPolicy.duration(2000,true).equals("2.0 s"));
        check(ExecutionResultPolicy.duration(-1,true).equals("Not available"));
        check(ExecutionResultPolicy.shouldCelebrate("SUCCEEDED",RUN,RUN,"",true));
        check(!ExecutionResultPolicy.shouldCelebrate("SUCCEEDED",RUN,RUN,RUN,true));
        check(!ExecutionResultPolicy.shouldCelebrate("SUCCEEDED",RUN,RUN,"",false));
        check(!ExecutionResultPolicy.shouldCelebrate("CANCELLED",RUN,RUN,"",true));
        check(!ExecutionResultPolicy.shouldCelebrate("SUCCEEDED",OTHER,RUN,"",true));
        check(ExecutionResultPolicy.title("SUCCEEDED",true,false).equals("执行完成 · 目标已核验"));
        check(ExecutionResultPolicy.title("SUCCEEDED",true,true).equals("Completed · targets verified"));
        check(!ExecutionResultPolicy.title("SUCCEEDED",false,false).contains("目标已核验"));
        check(ExecutionResultPolicy.title("CANCELLED",true,false).equals("已停止"));
        check(ExecutionResultPolicy.title("RUNNING",true,true).equals("Execution in progress"));
        check(ExecutionResultPolicy.title("UNKNOWN",true,false).equals("未确认完成"));
        System.out.println("ExecutionResultPolicyTest: "+checks+" checks passed");
    }
    private static void check(boolean value){checks++;if(!value)throw new AssertionError("check "+checks);}
}
