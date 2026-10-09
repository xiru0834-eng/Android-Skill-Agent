package edu.sydney.probe;
import java.util.*;

/** Known UI mechanics only. Schema, typed semantic goals and registry live elsewhere. */
final class TransferLabParameterAdapter {
    static void validateStart(String page){ParameterSkills.need(List.of("single","overview").contains(page),"BINDING_START");}
    static String group(String device){return "bedroom_light".equals(device)?"Lamp":"bedroom_fan".equals(device)?"Fan":"";}
    static int field(ParameterSkills.Call call){return call.skill.equals("SetBrightness")?1:call.skill.equals("SetFanSpeed")?3:call.device.equals("bedroom_light")?0:2;}
    static boolean supports(ParameterSkills.Binding b,String skill,String device){
        String group=group(device);if(group.isEmpty()||!ParameterSkills.NAMES.contains(skill))return false;
        if(!b.observed.contains("wf"+group+"Save"))return false;
        if(b.startPage.equals("overview")&&!b.observed.contains("wfOpen"+group))return false;
        if(skill.equals("SetPower"))return b.observed.contains("wf"+group+"Power");
        if(skill.equals("SetBrightness")&&!group.equals("Lamp")||skill.equals("SetFanSpeed")&&!group.equals("Fan"))return false;
        return b.observed.stream().anyMatch(id->id.startsWith("wf"+group+"Value"));
    }
    static void validate(ParameterSkills.Binding binding,ParameterSkills.Call call){
        ParameterSkills.need(call!=null&&binding.supports(call.skill,call.device),"UNBOUND_CAPABILITY");
        List<Object> options=new ArrayList<>();
        if(call.skill.equals("SetPower"))options.addAll(List.of("on","off"));
        else for(int option:FlexibleWorkflow.OPTIONS[field(call)])options.add(option);
        var entity=new SemanticSkills.Entity(call.device,call.device,List.of(),Set.of(call.skill));
        var catalog=new SemanticSkills.Catalog(List.of(entity));
        var environment=new SemanticCapabilities.Environment("transfer_lab",Map.of(call.device,Map.of(call.skill,SemanticCapabilities.Domain.values(options))));
        try{SemanticCapabilities.compile(catalog,environment,List.of(new SemanticSkills.Call(call.skill,call.device,call.value)));}
        catch(IllegalArgumentException error){
            String reason=error.getMessage();
            if(call.skill.equals("SetPower")&&(reason.equals("VALUE_TYPE")||reason.equals("VALUE_ENUM")))reason="POWER_STATE";
            else if(reason.equals("VALUE_TYPE"))reason="PARAMETER_INTEGER";
            else if(reason.equals("VALUE_RANGE"))reason=call.skill.equals("SetBrightness")?"PERCENT_RANGE":"UNSUPPORTED_VALUE";
            throw new IllegalArgumentException(reason,error);
        }
    }
    static ParameterSkills.Plan compile(ParameterSkills.Binding binding,List<ParameterSkills.Call> calls){
        ParameterSkills.need(binding!=null&&calls!=null&&!calls.isEmpty()&&calls.size()<=ParameterSkills.MAX_CALLS,"CALL_COUNT");
        for(var call:calls)validate(binding,call);
        var state=new FlexibleWorkflow.State(binding.startPage,new int[]{0,20,0,1});List<ParameterSkills.Step> steps=new ArrayList<>();
        for(var call:calls){
            String group=group(call.device);
            if(binding.startPage.equals("overview"))append(steps,state,"wfOpen"+group,null);
            String key="wf"+group+(call.skill.equals("SetPower")?"Power":"Value"+call.value);
            append(steps,state,key,call.skill.equals("SetPower")?call.value.equals("on"):true);
            append(steps,state,"wf"+group+"Save",null);
        }
        ParameterSkills.need(state.complete(),"PLAN_INCOMPLETE");return new ParameterSkills.Plan(steps,state);
    }
    private static void append(List<ParameterSkills.Step> steps,FlexibleWorkflow.State state,String id,Boolean desired){
        String page=state.page();steps.add(new ParameterSkills.Step(id,page,desired,state.apply(id,desired)));
    }
    static Map<String,Object> observedValues(int[] state){
        ParameterSkills.need(state!=null&&state.length==4,"STATE_SIZE");
        return Map.of("bedroom_light.power",state[0]==1?"on":"off","bedroom_light.brightnessPercent",state[1],
            "bedroom_fan.power",state[2]==1?"on":"off","bedroom_fan.fanSpeedLevel",state[3]);
    }
}
