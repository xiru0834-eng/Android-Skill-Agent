package edu.sydney.probe;
import java.util.List;

/** Model proposal only: no authority to create a skill or approve a binding. */
public final class LanguageDecision {
    public final String status,message;
    public final Boolean lamp,fan;
    public LanguageDecision(String status,String skill,Boolean lamp,Boolean fan,String message) {
        if(!List.of("invoke","clarify","reject").contains(status) || !"room_controls".equals(skill)
                || message==null || message.length()>1000
                || ("invoke".equals(status)!=(lamp!=null || fan!=null)))
            throw new IllegalArgumentException("INVALID_INTENT");
        this.status=status;this.lamp=lamp;this.fan=fan;this.message=message;
    }
    public List<Boolean> resolve(boolean currentLamp,boolean currentFan) {
        if(!"invoke".equals(status)) throw new IllegalArgumentException("NOT_EXECUTABLE");
        return List.of(lamp==null?currentLamp:lamp,fan==null?currentFan:fan);
    }
}
