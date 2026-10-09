package edu.sydney.probe;

import java.util.*;

/** Exhaustive initial-state matrix, not GUI runs or model interpretation evidence. */
public final class ParameterAcceptanceMatrixTest {
    private static int cases,checks;
    private static void eq(Object expected,Object actual){checks++;if(!Objects.deepEquals(expected,actual))throw new AssertionError(expected+" != "+actual);}
    private static ParameterSkills.Call call(String name,String device,Object value){return new ParameterSkills.Call(name,device,value);}
    private static Integer[] goals(List<ParameterSkills.Call> calls){
        Integer[] expected=new Integer[4];
        for(var call:calls){
            if(call.skill.equals("SetPower"))expected[call.device.equals("bedroom_light")?0:2]=call.value.equals("on")?1:0;
            else if(call.skill.equals("SetBrightness"))expected[1]=(Integer)call.value;
            else if(call.skill.equals("SetFanSpeed"))expected[3]=(Integer)call.value;
            else throw new AssertionError("Unexpected fixture skill");
        }
        return expected;
    }
    private static void rejects(String code,Runnable job){checks++;try{job.run();}catch(IllegalArgumentException e){eq(code,e.getMessage());return;}throw new AssertionError("Accepted "+code);}
    public static void main(String[] args){
        Set<String> ids=Set.of("wfLampPower","wfLampValue60","wfLampSave","wfOpenLamp","wfFanPower","wfFanValue1","wfFanSave","wfOpenFan");
        List<List<ParameterSkills.Call>> dataset=new ArrayList<>();
        for(int value:new int[]{20,40,60,80,100})dataset.add(List.of(call("SetBrightness","bedroom_light",value)));
        for(String device:List.of("bedroom_light","bedroom_fan"))for(String state:List.of("on","off"))dataset.add(List.of(call("SetPower",device,state)));
        for(int level:new int[]{1,2,3})dataset.add(List.of(call("SetFanSpeed","bedroom_fan",level)));
        dataset.add(List.of(call("SetBrightness","bedroom_light",20),call("SetBrightness","bedroom_light",100)));
        dataset.add(List.of(call("SetPower","bedroom_fan","on"),call("SetPower","bedroom_light","off"),call("SetFanSpeed","bedroom_fan",2)));
        dataset.add(List.of(call("SetPower","bedroom_light","on"),call("SetBrightness","bedroom_light",80),call("SetPower","bedroom_fan","off"),call("SetFanSpeed","bedroom_fan",1)));
        for(String layout:List.of("single","overview")){
            var binding=new ParameterSkills.Binding(layout,ids);
            for(int lamp:new int[]{0,1})for(int brightness:new int[]{20,40,60,80,100})for(int fan:new int[]{0,1})for(int speed:new int[]{1,2,3}){
                int[] initial={lamp,brightness,fan,speed};
                for(var calls:dataset){
                    Integer[] mask=goals(calls);int[] expected=initial.clone();
                    for(int i=0;i<4;i++)if(mask[i]!=null)expected[i]=mask[i];
                    var plan=ParameterSkills.compile(binding,calls);var state=new FlexibleWorkflow.State(layout,initial);
                    eq(mask,plan.goals);eq(calls.size()*(layout.equals("single")?2:3),plan.steps.size());
                    for(var step:plan.steps){eq(state.page(),step.page);state.apply(step.id,step.desired);}
                    eq(expected,state.saved());eq(true,state.complete());eq(layout,state.page());cases++;
                }
            }
            List<ParameterSkills.Call> maximum=new ArrayList<>();
            for(int i=0;i<32;i++)maximum.add(call("SetPower","bedroom_light",i%2==0?"on":"off"));
            eq(new Integer[]{0,null,null,null},ParameterSkills.compile(binding,maximum).goals);
            maximum.add(call("SetPower","bedroom_light","on"));rejects("CALL_COUNT",()->ParameterSkills.compile(binding,maximum));
            rejects("UNSUPPORTED_VALUE",()->ParameterSkills.compile(binding,List.of(call("SetPower","bedroom_light","on"),call("SetBrightness","bedroom_light",55))));
            eq(new int[]{1,100,1,3},new FlexibleWorkflow.State(layout,new int[]{1,100,1,3}).saved());
        }
        eq(1800,cases);
        System.out.println("ParameterAcceptanceMatrixTest PASS: syntheticCases="+cases+"; assertions="+checks+"; 15 sequences x 60 initial states x 2 layouts; GUI runs=0; model calls=0");
    }
}
