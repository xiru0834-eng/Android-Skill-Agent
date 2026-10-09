package edu.sydney.probe;

/** Bounded observation only; this policy never retries an input. */
final class WorkflowRecordingPolicy {
    private final long started;
    private final String before;
    private final boolean safeNoop;
    private final long budget;
    private String candidate;
    private long candidateSince;
    WorkflowRecordingPolicy(long started,String before,boolean safeNoop){this(started,before,safeNoop,1500);}
    WorkflowRecordingPolicy(long started,String before,boolean safeNoop,long budget){if(budget<1500||budget>10000)throw new IllegalArgumentException("OBSERVATION_BUDGET");this.started=started;this.before=before;this.safeNoop=safeNoop;this.budget=budget;}
    String observe(long now,String observed) {
        if(now-started>=budget)return "TIMEOUT";
        if(observed==null){candidate=null;return "WAIT";}
        if(!observed.equals(candidate)){candidate=observed;candidateSince=now;return "WAIT";}
        if(now-candidateSince<150)return "WAIT";
        if(!observed.equals(before))return "CHANGED";
        return safeNoop?"NOOP":"WAIT";
    }
    static boolean safeNoop(String id,boolean selected,String page) {
        if(id.equals("wfMulti")&&page.equals("overview"))return true;
        return selected&&(((page.equals("lamp")||page.equals("single"))&&id.matches("wfLampValue(20|40|60|80|100)"))
            ||((page.equals("fan")||page.equals("single"))&&id.matches("wfFanValue[123]")));
    }
    static String relation(String current,String saved) {
        if(saved==null||saved.isEmpty())return "暂无";
        return saved.equals(current)?"属于本次录制":"历史技能，与本次录制不同";
    }
}
