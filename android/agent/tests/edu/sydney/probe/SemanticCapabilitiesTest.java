package edu.sydney.probe;
import java.util.*;

public final class SemanticCapabilitiesTest {
    private static int checks;
    private static void eq(Object expected,Object actual){checks++;if(!Objects.equals(expected,actual))throw new AssertionError(expected+" != "+actual);}
    private static void rejects(String reason,Runnable task){checks++;try{task.run();}catch(IllegalArgumentException error){eq(reason,error.getMessage());return;}throw new AssertionError("accepted "+reason);}
    private static SemanticSkills.Catalog catalog(){
        List<SemanticSkills.Entity> entities=new ArrayList<>();
        for(String id:List.of("living_light","bedroom_light","aircon","fan","curtain","purifier","humidifier","exhaust"))entities.add(new SemanticSkills.Entity(id,id,List.of(),Set.of("SetPower","SetBrightness","SetTemperature","SetFanSpeed","SetCurtain","SetMode","SetTargetHumidity","SetColorTemperature")));
        return new SemanticSkills.Catalog(entities);
    }
    private static SemanticCapabilities.Environment environment(boolean continuous){
        Map<String,Map<String,SemanticCapabilities.Domain>> targets=new LinkedHashMap<>();
        for(String id:List.of("living_light","bedroom_light"))targets.put(id,Map.of(
            "SetPower",SemanticCapabilities.Domain.values(List.of("on","off")),
            "SetBrightness",continuous?SemanticCapabilities.Domain.range(0,100,1):SemanticCapabilities.Domain.values(List.of(20,40,60,80,100)),
            "SetColorTemperature",continuous?SemanticCapabilities.Domain.range(2700,6500,100):SemanticCapabilities.Domain.values(List.of(2700,4000,6500))));
        targets.put("aircon",Map.of("SetTemperature",SemanticCapabilities.Domain.range(16,30,1),"SetMode",SemanticCapabilities.Domain.values(List.of("cool","heat","auto"))));
        targets.put("fan",Map.of("SetFanSpeed",SemanticCapabilities.Domain.range(1,continuous?5:3,1)));
        targets.put("curtain",Map.of("SetCurtain",continuous?SemanticCapabilities.Domain.range(0,100,1):SemanticCapabilities.Domain.values(List.of(0,20,40,60,80,100))));
        targets.put("purifier",Map.of("SetMode",SemanticCapabilities.Domain.values(List.of("auto","sleep"))));
        targets.put("humidifier",Map.of("SetTargetHumidity",continuous?SemanticCapabilities.Domain.range(40,70,5):SemanticCapabilities.Domain.values(List.of(40,50,60,70))));
        targets.put("exhaust",Map.of("SetPower",SemanticCapabilities.Domain.values(List.of("on","off"))));
        return new SemanticCapabilities.Environment(continuous?"alternative":"discrete",targets);
    }
    private static void accepted(SemanticCapabilities.Environment env,String skill,String entity,Object value){
        var call=new SemanticSkills.Call(skill,entity,value);var plan=SemanticCapabilities.compile(catalog(),env,List.of(call));
        eq(value,plan.goals.get(call.propertyKey()));eq(List.of(call),plan.calls);
    }
    public static void main(String[] args){
        String hash=SemanticSkills.registryHash();var a=environment(false);var b=environment(true);
        for(var env:List.of(a,b)){
            for(String entity:List.of("living_light","bedroom_light","exhaust"))for(String state:List.of("on","off"))accepted(env,"SetPower",entity,state);
            for(String entity:List.of("living_light","bedroom_light"))for(int percent:new int[]{20,40,60,80,100})accepted(env,"SetBrightness",entity,percent);
            for(int celsius:new int[]{16,20,24,30})accepted(env,"SetTemperature","aircon",celsius);
            for(int speed:new int[]{1,2,3})accepted(env,"SetFanSpeed","fan",speed);
            for(int position:new int[]{0,20,60,100})accepted(env,"SetCurtain","curtain",position);
            for(String mode:List.of("cool","heat","auto"))accepted(env,"SetMode","aircon",mode);
            for(String mode:List.of("auto","sleep"))accepted(env,"SetMode","purifier",mode);
            for(int humidity:new int[]{40,50,60,70})accepted(env,"SetTargetHumidity","humidifier",humidity);
            for(int kelvin:new int[]{2700,4000,6500})accepted(env,"SetColorTemperature","living_light",kelvin);
        }
        // A semantically valid value must not be silently rounded by the environment validator.
        var unsupported=List.of(new SemanticSkills.Call("SetBrightness","living_light",55));
        eq(55,SemanticSkills.compile(catalog(),unsupported).goals.get("living_light.brightnessPercent"));
        rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog(),a,unsupported));
        accepted(b,"SetBrightness","living_light",55);accepted(b,"SetFanSpeed","fan",5);
        accepted(b,"SetColorTemperature","living_light",3800);accepted(b,"SetTargetHumidity","humidifier",55);
        for(var call:List.of(new SemanticSkills.Call("SetFanSpeed","fan",5),new SemanticSkills.Call("SetColorTemperature","living_light",3800),new SemanticSkills.Call("SetTargetHumidity","humidifier",55))){
            rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog(),a,List.of(call)));
        }
        rejects("UNSUPPORTED_VALUE",()->accepted(a,"SetTemperature","aircon",15));
        rejects("UNSUPPORTED_VALUE",()->accepted(b,"SetColorTemperature","living_light",3801));
        rejects("UNSUPPORTED_VALUE",()->accepted(a,"SetMode","aircon","sleep"));
        rejects("UNBOUND_CAPABILITY",()->accepted(a,"SetBrightness","fan",80));
        rejects("UNBOUND_ENTITY",()->{
            var catalog=new SemanticSkills.Catalog(List.of(new SemanticSkills.Entity("desk_light","Desk",List.of(),Set.of("SetPower"))));
            SemanticCapabilities.compile(catalog,a,List.of(new SemanticSkills.Call("SetPower","desk_light","on")));
        });
        var calls=List.of(new SemanticSkills.Call("SetPower","living_light","on"),new SemanticSkills.Call("SetBrightness","bedroom_light",80),new SemanticSkills.Call("SetMode","purifier","sleep"),new SemanticSkills.Call("SetCurtain","curtain",20));
        eq(SemanticCapabilities.compile(catalog(),a,calls).goals,SemanticCapabilities.compile(catalog(),b,calls).goals);eq(hash,SemanticSkills.registryHash());
        rejects("DOMAIN_RANGE",()->SemanticCapabilities.Domain.range(10,0,1));
        rejects("DOMAIN_RANGE",()->SemanticCapabilities.Domain.range(0,100,0));
        rejects("DOMAIN_RANGE",()->SemanticCapabilities.Domain.range(0,100,3));
        rejects("DOMAIN_VALUES",()->SemanticCapabilities.Domain.values(List.of()));
        rejects("DOMAIN_VALUES",()->SemanticCapabilities.Domain.values(List.of(20,20)));
        rejects("VALUE_TYPE",()->new SemanticCapabilities.Environment("invalid",Map.of("light",Map.of("SetBrightness",SemanticCapabilities.Domain.values(List.of("20"))))));
        rejects("VALUE_RANGE",()->new SemanticCapabilities.Environment("invalid",Map.of("light",Map.of("SetBrightness",SemanticCapabilities.Domain.range(-1,100,1)))));
        rejects("DOMAIN_KIND",()->new SemanticCapabilities.Environment("invalid",Map.of("light",Map.of("SetMode",SemanticCapabilities.Domain.range(1,3,1)))));
        rejects("ENVIRONMENT_ID",()->new SemanticCapabilities.Environment("../escape",Map.of("light",Map.of("SetPower",SemanticCapabilities.Domain.values(List.of("on"))))));
        Map<String,SemanticCapabilities.Domain> mutable=new HashMap<>();mutable.put("SetPower",SemanticCapabilities.Domain.values(List.of("on")));Map<String,Map<String,SemanticCapabilities.Domain>> source=new HashMap<>();source.put("living_light",mutable);
        var copied=new SemanticCapabilities.Environment("copy",source);mutable.clear();source.clear();accepted(copied,"SetPower","living_light","on");
        rejects("ENVIRONMENT_NULL",()->SemanticCapabilities.compile(catalog(),null,calls));
        rejects("ENVIRONMENT_TARGETS",()->new SemanticCapabilities.Environment("empty",Map.of()));
        rejects("ENVIRONMENT_TARGETS",()->new SemanticCapabilities.Environment("empty",null));
        rejects("DOMAIN_VALUES",()->SemanticCapabilities.Domain.values(null));
        rejects("DOMAIN_VALUES",()->SemanticCapabilities.Domain.values(Arrays.asList((Object)null)));
        rejects("DOMAIN_VALUES",()->SemanticCapabilities.Domain.values(Collections.nCopies(257,1)));
        rejects("UNKNOWN_SKILL",()->new SemanticCapabilities.Environment("unknown",Map.of("light",Map.of("Guess",SemanticCapabilities.Domain.values(List.of(20))))));
        Map<String,SemanticCapabilities.Domain> noDomain=new HashMap<>();noDomain.put("SetPower",null);
        rejects("DOMAIN_NULL",()->new SemanticCapabilities.Environment("null_domain",Map.of("light",noDomain)));
        try{copied.domains.get("living_light").clear();throw new AssertionError("mutable capabilities");}catch(UnsupportedOperationException expected){checks++;}
        try{copied.domains.clear();throw new AssertionError("mutable environment");}catch(UnsupportedOperationException expected){checks++;}
        var overflow=SemanticCapabilities.Domain.range(Integer.MIN_VALUE,Integer.MAX_VALUE,1);
        eq(true,overflow.accepts(Integer.MAX_VALUE));eq(true,overflow.accepts(Integer.MIN_VALUE));eq(false,overflow.accepts(1L));
        System.out.println("SemanticCapabilitiesTest passed: "+checks+"; structural cases, not GUI runs");
    }
}
