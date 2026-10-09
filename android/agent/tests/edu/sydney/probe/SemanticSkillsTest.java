package edu.sydney.probe;
import java.util.*;

public final class SemanticSkillsTest {
    private static int checks;
    private static void eq(Object expected,Object actual){checks++;if(!Objects.equals(expected,actual))throw new AssertionError(expected+" != "+actual);}
    private static void rejects(String reason,Runnable task){
        checks++;try{task.run();}catch(IllegalArgumentException error){eq(reason,error.getMessage());return;}throw new AssertionError("accepted "+reason);
    }
    private static SemanticSkills.Entity entity(String id,String name,Set<String> capabilities,String... aliases){return new SemanticSkills.Entity(id,name,List.of(aliases),capabilities);}
    public static void main(String[] args){
        eq(8,SemanticSkills.definitions().size());
        var catalog=new SemanticSkills.Catalog(List.of(
            entity("living_light","客厅灯",Set.of("SetPower","SetBrightness","SetColorTemperature"),"living room light"),
            entity("bedroom_light","卧室灯",Set.of("SetPower","SetBrightness","SetColorTemperature"),"bedroom light","lamp"),
            entity("aircon","空调",Set.of("SetPower","SetTemperature","SetMode"),"air conditioner"),
            entity("fan","风扇",Set.of("SetPower","SetFanSpeed"),"fan"),
            entity("curtain","窗帘",Set.of("SetCurtain"),"curtain"),
            entity("purifier","净化器",Set.of("SetPower","SetFanSpeed","SetMode"),"air purifier"),
            entity("humidifier","加湿器",Set.of("SetPower","SetTargetHumidity"),"humidifier"),
            entity("exhaust","排风扇",Set.of("SetPower","SetFanSpeed"),"exhaust fan","lamp")));
        eq("living_light",catalog.resolve("客厅灯"));eq("living_light",catalog.resolve(" Living Room Light "));
        rejects("AMBIGUOUS_ENTITY",()->catalog.resolve("lamp"));rejects("UNKNOWN_ENTITY",()->catalog.resolve("desk lamp"));
        var samples=List.of(
            new SemanticSkills.Call("SetPower","living_light","on"),
            new SemanticSkills.Call("SetBrightness","bedroom_light",80),
            new SemanticSkills.Call("SetTemperature","aircon",24),
            new SemanticSkills.Call("SetFanSpeed","fan",4),
            new SemanticSkills.Call("SetCurtain","curtain",60),
            new SemanticSkills.Call("SetMode","purifier","sleep"),
            new SemanticSkills.Call("SetTargetHumidity","humidifier",55),
            new SemanticSkills.Call("SetColorTemperature","living_light",4000));
        var plan=SemanticSkills.compile(catalog,samples);
        eq(samples,plan.calls);eq(8,plan.goals.size());eq(80,plan.goals.get("bedroom_light.brightnessPercent"));
        eq("on",plan.goals.get("living_light.power"));eq(24,plan.goals.get("aircon.temperatureCelsius"));
        eq("sleep",plan.goals.get("purifier.operatingMode"));eq(55,plan.goals.get("humidifier.targetHumidityPercent"));
        eq(4000,plan.goals.get("living_light.colorTemperatureKelvin"));
        for(var call:samples){
            var definition=SemanticSkills.definition(call.skill);
            var parsed=SemanticSkills.parse(call.skill,Map.of("device",call.device,definition.argument,call.value));
            eq(call,parsed);SemanticSkills.compile(catalog,List.of(parsed));
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(call.skill,Map.of("device",call.device,definition.argument,call.value,"x",1)));
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(call.skill,Map.of("device",call.device)));
            rejects("VALUE_TYPE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call(call.skill,call.device,true))));
        }
        var repeated=new ArrayList<>(samples);repeated.add(new SemanticSkills.Call("SetBrightness","bedroom_light",20));
        var last=SemanticSkills.compile(catalog,repeated);eq(9,last.calls.size());eq(8,last.goals.size());eq(20,last.goals.get("bedroom_light.brightnessPercent"));
        eq(samples.get(1),last.calls.get(1));eq(repeated.get(8),last.calls.get(8));
        for(String id:List.of("living_light","bedroom_light","aircon","fan","purifier","humidifier","exhaust")){
            for(String state:List.of("on","off"))eq(state,SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetPower",id,state))).goals.get(id+".power"));
        }
        for(int percent:new int[]{0,20,40,60,80,100}){
            for(String skill:List.of("SetBrightness","SetCurtain","SetTargetHumidity")){
                String id=skill.equals("SetBrightness")?"living_light":skill.equals("SetCurtain")?"curtain":"humidifier";
                eq(percent,SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call(skill,id,percent))).goals.get(id+"."+SemanticSkills.definition(skill).property));
            }
        }
        for(Object bad:List.of("80",80.0,80L,true))rejects("VALUE_TYPE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetBrightness","living_light",bad))));
        for(int bad:new int[]{-1,101})rejects("VALUE_RANGE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetBrightness","living_light",bad))));
        rejects("VALUE_RANGE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetTemperature","aircon",-274))));
        rejects("VALUE_RANGE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetFanSpeed","fan",0))));
        rejects("VALUE_RANGE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetColorTemperature","living_light",0))));
        rejects("VALUE_ENUM",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetPower","fan","ON"))));
        rejects("VALUE_ENUM",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetMode","aircon","sleep; click"))));
        rejects("UNKNOWN_SKILL",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("OpenEverything","fan","on"))));
        rejects("UNKNOWN_ENTITY",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetPower","other_fan","on"))));
        rejects("UNSUPPORTED_CAPABILITY",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call("SetBrightness","fan",80))));
        rejects("CALL_COUNT",()->SemanticSkills.compile(catalog,List.of()));
        rejects("CALL_COUNT",()->SemanticSkills.compile(catalog,Collections.nCopies(33,samples.get(0))));
        eq(32,SemanticSkills.compile(catalog,Collections.nCopies(32,samples.get(0))).calls.size());
        rejects("DUPLICATE_ENTITY",()->new SemanticSkills.Catalog(List.of(catalog.entities.get(0),catalog.entities.get(0))));
        rejects("UNKNOWN_SKILL",()->entity("new","新设备",Set.of("CustomCode")));
        String digest=SemanticSkills.registryHash();eq(64,digest.length());
        var otherCatalog=new SemanticSkills.Catalog(List.of(entity("desk_light","书桌灯",Set.of("SetPower","SetBrightness"),"desk light")));
        eq(20,SemanticSkills.compile(otherCatalog,List.of(new SemanticSkills.Call("SetBrightness","desk_light",20))).goals.get("desk_light.brightnessPercent"));
        eq(digest,SemanticSkills.registryHash());
        try{plan.goals.put("new",1);throw new AssertionError("mutable plan");}catch(UnsupportedOperationException expected){checks++;}
        rejects("CATALOG_NULL",()->SemanticSkills.compile(null,samples));
        rejects("CALL_COUNT",()->SemanticSkills.compile(catalog,null));
        rejects("CALL_NULL",()->SemanticSkills.compile(catalog,Arrays.asList((SemanticSkills.Call)null)));
        rejects("CATALOG_SIZE",()->new SemanticSkills.Catalog(List.of()));
        rejects("CATALOG_SIZE",()->new SemanticSkills.Catalog(null));
        rejects("ENTITY_NULL",()->new SemanticSkills.Catalog(Arrays.asList((SemanticSkills.Entity)null)));
        rejects("ENTITY_ID",()->entity("lamp.power","Lamp",Set.of("SetPower")));
        rejects("ENTITY_NAME",()->entity("lamp","　",Set.of("SetPower")));
        rejects("ENTITY_NAME",()->entity("lamp","\n",Set.of("SetPower")));
        rejects("ENTITY_ALIASES",()->new SemanticSkills.Entity("lamp","Lamp",null,Set.of("SetPower")));
        rejects("ENTITY_CAPABILITIES",()->entity("lamp","Lamp",Set.of()));
        rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse("SetPower",null));
        rejects("VALUE_TYPE",()->SemanticSkills.parse("SetBrightness",Map.of("device","living_light","percent",80.0)));
        Map<String,Object> nullArgs=new HashMap<>();nullArgs.put("device","living_light");nullArgs.put("percent",null);
        rejects("VALUE_TYPE",()->SemanticSkills.parse("SetBrightness",nullArgs));
        System.out.println("SemanticSkillsTest passed: "+checks);
    }
}
