package edu.sydney.probe;
import java.util.*;

/** Compatibility call/plan facade. Semantic registry is independent; lab UI lives in its adapter. */
final class ParameterSkills {
    static final List<String> NAMES=List.of("SetPower","SetBrightness","SetFanSpeed");
    static final int MAX_CALLS=SemanticSkills.MAX_CALLS;
    static void need(boolean value,String reason){if(!value)throw new IllegalArgumentException(reason);}
    static final class Call {
        final String skill,device;final Object value;
        Call(String skill,String device,Object value){this.skill=skill;this.device=device;this.value=value;}
    }
    static final class Binding {
        final String startPage;final Set<String> observed;
        Binding(String startPage,Set<String> ids){TransferLabParameterAdapter.validateStart(startPage);this.startPage=startPage;observed=Set.copyOf(ids);}
        String group(String device){return TransferLabParameterAdapter.group(device);}
        boolean supports(String skill,String device){return TransferLabParameterAdapter.supports(this,skill,device);}
    }
    static final class Step {
        final String id,page,afterPage,operation;final Boolean desired;final Integer[] commitGoals;
        Step(String id,String page,Boolean desired,FlexibleWorkflow.Action action){this.id=id;this.page=page;this.desired=desired;afterPage=action.afterPage;operation=action.operation;commitGoals=action.commitGoals.clone();}
    }
    static final class Plan {
        final List<Step> steps;final Integer[] goals;final String endPage;
        Plan(List<Step> steps,FlexibleWorkflow.State state){this.steps=List.copyOf(steps);goals=state.goals();endPage=state.page();}
    }
    static int field(Call call){return TransferLabParameterAdapter.field(call);}
    static void validate(Binding binding,Call call){TransferLabParameterAdapter.validate(binding,call);}
    static Plan compile(Binding binding,List<Call> calls){return TransferLabParameterAdapter.compile(binding,calls);}
}
