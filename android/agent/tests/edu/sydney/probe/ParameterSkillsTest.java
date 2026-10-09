package edu.sydney.probe;
import java.util.*;

public final class ParameterSkillsTest {
    private static int checks;
    private static void eq(Object expected,Object actual){checks++;if(!Objects.deepEquals(expected,actual))throw new AssertionError(expected+" != "+actual);}
    private static void rejects(Runnable task){checks++;try{task.run();}catch(IllegalArgumentException ok){return;}throw new AssertionError("accepted invalid input");}
    public static void main(String[] args){
        Set<String> ids=Set.of("wfLampPower","wfLampValue60","wfLampSave","wfOpenLamp","wfFanPower","wfFanValue1","wfFanSave","wfOpenFan");
        for(String layout:List.of("single","overview")){
            var binding=new ParameterSkills.Binding(layout,ids);
            for(int value:new int[]{20,40,60,80,100}){
                var plan=ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetBrightness","bedroom_light",value)));
                eq(new Integer[]{null,value,null,null},plan.goals);
                eq(layout,plan.endPage);eq("wfLampValue"+value,plan.steps.get(layout.equals("single")?0:1).id);
            }
            var calls=List.of(new ParameterSkills.Call("SetPower","bedroom_light","on"),new ParameterSkills.Call("SetBrightness","bedroom_light",80),new ParameterSkills.Call("SetPower","bedroom_fan","off"),new ParameterSkills.Call("SetFanSpeed","bedroom_fan",2));
            var plan=ParameterSkills.compile(binding,calls);eq(new Integer[]{1,80,0,2},plan.goals);
            for(int power:new int[]{0,1})for(int light:FlexibleWorkflow.OPTIONS[1])for(int fan:new int[]{0,1})for(int speed:new int[]{1,2,3}){
                var state=new FlexibleWorkflow.State(layout,new int[]{power,light,fan,speed});
                for(var step:plan.steps){eq(state.page(),step.page);state.apply(step.id,step.desired);}
                eq(new int[]{1,80,0,2},state.saved());eq(true,state.complete());
            }
            var last=ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetPower","bedroom_light","on"),new ParameterSkills.Call("SetPower","bedroom_light","off")));
            eq(new Integer[]{0,null,null,null},last.goals);
            for(Object bad:List.of(55,101,-1,true,"80",80.0))rejects(()->ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetBrightness","bedroom_light",bad))));
            rejects(()->ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetTemperature","bedroom_ac",28))));
            rejects(()->ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetPower","living_room_light","on"))));
            rejects(()->ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetPower","bedroom_light",true))));
            rejects(()->ParameterSkills.compile(binding,List.of(new ParameterSkills.Call("SetFanSpeed","bedroom_fan",4))));
            rejects(()->ParameterSkills.compile(binding,List.of()));
        }
        var lampOnly=new ParameterSkills.Binding("single",Set.of("wfLampValue60","wfLampSave"));
        eq(false,lampOnly.supports("SetPower","bedroom_light"));
        rejects(()->ParameterSkills.compile(lampOnly,List.of(new ParameterSkills.Call("SetPower","bedroom_light","on"))));
        rejects(()->new ParameterSkills.Binding("lamp",ids));
        // The lab adapter keeps its existing error contract while adopting semantic validation.
        var adapter=new ParameterSkills.Binding("single",ids);
        try{ParameterSkills.validate(adapter,new ParameterSkills.Call("SetBrightness","bedroom_light",true));throw new AssertionError("boolean percent");}
        catch(IllegalArgumentException expected){eq("PARAMETER_INTEGER",expected.getMessage());}
        try{ParameterSkills.validate(adapter,new ParameterSkills.Call("SetBrightness","bedroom_light",101));throw new AssertionError("out of range");}
        catch(IllegalArgumentException expected){eq("PERCENT_RANGE",expected.getMessage());}
        System.out.println("ParameterSkillsTest passed: "+checks);
    }
}
