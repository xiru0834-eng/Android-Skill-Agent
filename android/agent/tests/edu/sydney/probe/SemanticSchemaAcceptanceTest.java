package edu.sydney.probe;

import java.util.*;

/** Frozen semantic acceptance: expansion and filling contracts, not GUI/model accuracy. */
public final class SemanticSchemaAcceptanceTest {
    private static int assertions, cases;
    private static void eq(Object expected,Object actual){
        assertions++;if(!Objects.equals(expected,actual))throw new AssertionError(expected+" != "+actual);
    }
    private static void rejects(String reason,Runnable task){
        cases++;
        try{task.run();}catch(IllegalArgumentException error){eq(reason,error.getMessage());return;}
        throw new AssertionError("Accepted "+reason);
    }
    private static Set<String> allSkills(){
        Set<String> names=new LinkedHashSet<>();
        for(var d:SemanticSkills.definitions())names.add(d.name);
        return names;
    }
    private static SemanticSkills.Entity entity(String id){
        return new SemanticSkills.Entity(id,"设备 "+id,List.of("Device "+id),allSkills());
    }
    private static SemanticSkills.Catalog catalog(int count){
        List<SemanticSkills.Entity> entities=new ArrayList<>();
        for(int i=0;i<count;i++)entities.add(entity("device_"+i));
        return new SemanticSkills.Catalog(entities);
    }
    private static Object sample(String skill){
        switch(skill){
            case "SetPower":return "on";
            case "SetBrightness":return 80;
            case "SetTemperature":return 24;
            case "SetFanSpeed":return 4;
            case "SetCurtain":return 60;
            case "SetMode":return "sleep";
            case "SetTargetHumidity":return 55;
            case "SetColorTemperature":return 4000;
            default:throw new AssertionError("Sample required for "+skill);
        }
    }
    private static Map<String,SemanticCapabilities.Domain> domains(boolean continuous){
        return Map.of(
            "SetPower",SemanticCapabilities.Domain.values(List.of("on","off")),
            "SetBrightness",continuous?SemanticCapabilities.Domain.range(0,100,1):SemanticCapabilities.Domain.values(List.of(20,40,60,80,100)),
            "SetTemperature",SemanticCapabilities.Domain.range(16,30,1),
            "SetFanSpeed",SemanticCapabilities.Domain.range(1,5,1),
            "SetCurtain",continuous?SemanticCapabilities.Domain.range(0,100,1):SemanticCapabilities.Domain.range(0,100,20),
            "SetMode",SemanticCapabilities.Domain.values(List.of("auto","sleep")),
            "SetTargetHumidity",continuous?SemanticCapabilities.Domain.range(0,100,1):SemanticCapabilities.Domain.range(40,70,5),
            "SetColorTemperature",SemanticCapabilities.Domain.range(2700,6500,100));
    }
    private static SemanticCapabilities.Environment environment(int count,boolean continuous){
        Map<String,Map<String,SemanticCapabilities.Domain>> entries=new LinkedHashMap<>();
        for(int i=0;i<count;i++)entries.put("device_"+i,domains(continuous));
        return new SemanticCapabilities.Environment(continuous?"continuous":"discrete",entries);
    }
    private static void exact(SemanticSkills.Catalog catalog,SemanticCapabilities.Environment env,String skill,String device,Object value){
        cases++;
        var d=SemanticSkills.definition(skill);
        var call=SemanticSkills.parse(skill,Map.of("device",device,d.argument,value));
        var plan=SemanticCapabilities.compile(catalog,env,List.of(call));
        eq(value,call.value);eq(device,call.device);eq(skill,call.skill);
        eq(List.of(call),plan.calls);eq(Map.of(device+"."+d.property,value),plan.goals);
    }
    private static void expansion(){
        String hash=SemanticSkills.registryHash();
        for(int count:new int[]{1,128}){
            var catalog=catalog(count);var env=environment(count,true);
            for(int i=0;i<count;i++){
                String device="device_"+i;
                cases++;eq(device,catalog.resolve("设备 "+device));eq(device,catalog.resolve(" Device "+device+" "));
                for(var definition:SemanticSkills.definitions())exact(catalog,env,definition.name,device,sample(definition.name));
            }
            eq(hash,SemanticSkills.registryHash());
        }
        rejects("CATALOG_SIZE",()->catalog(0));rejects("CATALOG_SIZE",()->catalog(129));
    }
    private static void fillContracts(){
        var catalog=catalog(1);var env=environment(1,true);
        for(var d:SemanticSkills.definitions()){
            Object value=sample(d.name);
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(d.name,Map.of(d.argument,value)));
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(d.name,Map.of("device","device_0")));
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(d.name,Map.of("device","device_0",d.argument,value,"x",1)));
            rejects("ARGUMENT_FIELDS",()->SemanticSkills.parse(d.name,Map.of("device","device_0",d.argument,value,"resource_id","target")));
            for(Object wrong:d.kind.equals("integer")?List.of(true,24.0,24L,"24"):List.of(true,24,24.0)){
                rejects("VALUE_TYPE",()->SemanticSkills.parse(d.name,Map.of("device","device_0",d.argument,wrong)));
            }
            Map<String,Object> nullValue=new HashMap<>();nullValue.put("device","device_0");nullValue.put(d.argument,null);
            rejects("VALUE_TYPE",()->SemanticSkills.parse(d.name,nullValue));
            Map<String,Object> nullDevice=new HashMap<>();nullDevice.put("device",null);nullDevice.put(d.argument,value);
            rejects("ENTITY_ID",()->SemanticSkills.parse(d.name,nullDevice));
            rejects("ENTITY_ID",()->SemanticSkills.parse(d.name,Map.of("device","../../target",d.argument,value)));
            rejects("UNKNOWN_ENTITY",()->SemanticCapabilities.compile(catalog,env,List.of(new SemanticSkills.Call(d.name,"missing",value))));
            var powerOnly=new SemanticSkills.Catalog(List.of(new SemanticSkills.Entity("device_0","设备",List.of(),Set.of("SetPower"))));
            if(!d.name.equals("SetPower"))rejects("UNSUPPORTED_CAPABILITY",()->SemanticCapabilities.compile(powerOnly,env,List.of(new SemanticSkills.Call(d.name,"device_0",value))));
        }
        var legal=new SemanticSkills.Call("SetPower","device_0","on");
        // The compiler must reject the entire list, not yield the valid prefix.
        rejects("VALUE_RANGE",()->SemanticCapabilities.compile(catalog,env,List.of(legal,new SemanticSkills.Call("SetBrightness","device_0",101))));
        rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,environment(1,false),List.of(legal,new SemanticSkills.Call("SetBrightness","device_0",55))));
        rejects("UNKNOWN_SKILL",()->SemanticSkills.parse("GeneratedClick",Map.of("device","device_0","code","click()")));
    }
    private static void domainsAndBounds(){
        String hash=SemanticSkills.registryHash();var catalog=catalog(1);var a=environment(1,false);var b=environment(1,true);
        for(String skill:List.of("SetBrightness","SetCurtain","SetTargetHumidity")){
            for(int value=0;value<=100;value++){
                exact(catalog,b,skill,"device_0",value);
                boolean supported=skill.equals("SetBrightness")?value>=20&&value%20==0:skill.equals("SetCurtain")?value%20==0:value>=40&&value<=70&&value%5==0;
                final int candidate=value;
                if(supported)exact(catalog,a,skill,"device_0",candidate);
                else rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,a,List.of(new SemanticSkills.Call(skill,"device_0",candidate))));
            }
            for(int value:new int[]{Integer.MIN_VALUE,-1,101,Integer.MAX_VALUE})rejects("VALUE_RANGE",()->SemanticSkills.compile(catalog,List.of(new SemanticSkills.Call(skill,"device_0",value))));
        }
        for(int value=15;value<=31;value++){
            final int candidate=value;
            if(value>=16&&value<=30)exact(catalog,b,"SetTemperature","device_0",value);
            else rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,b,List.of(new SemanticSkills.Call("SetTemperature","device_0",candidate))));
        }
        for(int value=1;value<=6;value++){
            final int candidate=value;
            if(value<=5)exact(catalog,b,"SetFanSpeed","device_0",value);
            else rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,b,List.of(new SemanticSkills.Call("SetFanSpeed","device_0",candidate))));
        }
        for(int value:new int[]{2600,2700,3800,3801,6500,6600}){
            if(value>=2700&&value<=6500&&value%100==0)exact(catalog,b,"SetColorTemperature","device_0",value);
            else rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,b,List.of(new SemanticSkills.Call("SetColorTemperature","device_0",value))));
        }
        for(String value:List.of("auto","sleep"))exact(catalog,b,"SetMode","device_0",value);
        rejects("UNSUPPORTED_VALUE",()->SemanticCapabilities.compile(catalog,b,List.of(new SemanticSkills.Call("SetMode","device_0","heat"))));
        for(String value:List.of("on","off"))exact(catalog,b,"SetPower","device_0",value);
        rejects("VALUE_ENUM",()->SemanticSkills.parse("SetPower",Map.of("device","device_0","state","ON")));
        rejects("VALUE_ENUM",()->SemanticSkills.parse("SetMode",Map.of("device","device_0","mode","sleep;click")));
        eq(hash,SemanticSkills.registryHash());
    }
    private static void orderedAndImmutable(){
        var catalog=catalog(2);var env=environment(2,true);
        List<SemanticSkills.Call> input=new ArrayList<>(List.of(
            new SemanticSkills.Call("SetBrightness","device_0",20),
            new SemanticSkills.Call("SetBrightness","device_1",40),
            new SemanticSkills.Call("SetBrightness","device_0",100)));
        List<SemanticSkills.Call> original=List.copyOf(input);
        var plan=SemanticCapabilities.compile(catalog,env,input);cases++;
        eq(original,plan.calls);eq(Map.of("device_0.brightnessPercent",100,"device_1.brightnessPercent",40),plan.goals);
        input.clear();eq(original,plan.calls);
        try{plan.calls.clear();throw new AssertionError("Mutable calls");}catch(UnsupportedOperationException expected){assertions++;}
        try{plan.goals.clear();throw new AssertionError("Mutable goals");}catch(UnsupportedOperationException expected){assertions++;}
        List<SemanticSkills.Entity> mutable=new ArrayList<>(catalog.entities);var copied=new SemanticSkills.Catalog(mutable);mutable.clear();eq(2,copied.entities.size());
        List<Object> values=new ArrayList<>(List.of(20,80));var domain=SemanticCapabilities.Domain.values(values);values.clear();eq(true,domain.accepts(20));eq(false,domain.accepts(60));
        rejects("CALL_COUNT",()->SemanticCapabilities.compile(catalog,env,List.of()));
        cases++;eq(32,SemanticCapabilities.compile(catalog,env,Collections.nCopies(32,original.get(0))).calls.size());
        rejects("CALL_COUNT",()->SemanticCapabilities.compile(catalog,env,Collections.nCopies(33,original.get(0))));
    }
    public static void main(String[] args){
        expansion();fillContracts();domainsAndBounds();orderedAndImmutable();
        System.out.println("SemanticSchemaAcceptanceTest passed: "+cases+" structural cases; "+assertions+" assertions; 0 GUI runs; 0 model requests");
    }
}
