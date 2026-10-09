package edu.sydney.probe;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

/** Domain contracts only. Environment capability checks and UI operations live elsewhere. */
final class SemanticSkills {
    static final int MAX_CALLS=32;
    private static void need(boolean valid,String reason){if(!valid)throw new IllegalArgumentException(reason);}
    private static boolean identifier(String value){return value!=null&&value.matches("[a-z][a-z0-9_]{0,63}");}
    private static boolean label(String value){return value!=null&&value.length()<=80&&value.chars().anyMatch(c->!Character.isWhitespace(c))&&value.chars().noneMatch(Character::isISOControl);}

    static final class Definition {
        final String name,argument,property,kind;
        final int min,max;
        final Set<String> choices;
        private Definition(String name,String argument,String property,String kind,int min,int max,Set<String> choices){
            this.name=name;this.argument=argument;this.property=property;this.kind=kind;this.min=min;this.max=max;this.choices=Set.copyOf(choices);
        }
        void validate(Object value){
            if(kind.equals("integer")){
                need(value instanceof Integer,"VALUE_TYPE");int number=(Integer)value;
                need(number>=min&&number<=max,"VALUE_RANGE");
            }else{
                need(value instanceof String,"VALUE_TYPE");String text=(String)value;
                need(kind.equals("enum")?choices.contains(text):text.matches("[a-z][a-z0-9_]{0,31}"),"VALUE_ENUM");
            }
        }
    }
    private static Definition number(String name,String argument,String property,int min,int max){return new Definition(name,argument,property,"integer",min,max,Set.of());}
    private static final Map<String,Definition> REGISTRY=registry();
    private static Map<String,Definition> registry(){
        Map<String,Definition> result=new LinkedHashMap<>();
        for(Definition definition:List.of(
            new Definition("SetPower","state","power","enum",0,0,Set.of("on","off")),
            number("SetBrightness","percent","brightnessPercent",0,100),
            number("SetTemperature","celsius","temperatureCelsius",-273,Integer.MAX_VALUE),
            number("SetFanSpeed","level","fanSpeedLevel",1,Integer.MAX_VALUE),
            number("SetCurtain","position","curtainPositionPercent",0,100),
            new Definition("SetMode","mode","operatingMode","identifier",0,0,Set.of()),
            number("SetTargetHumidity","percent","targetHumidityPercent",0,100),
            number("SetColorTemperature","kelvin","colorTemperatureKelvin",1,Integer.MAX_VALUE)))result.put(definition.name,definition);
        return Collections.unmodifiableMap(result);
    }
    static List<Definition> definitions(){return List.copyOf(REGISTRY.values());}
    static Definition definition(String name){Definition result=REGISTRY.get(name);need(result!=null,"UNKNOWN_SKILL");return result;}
    static String registryHash(){
        StringBuilder canonical=new StringBuilder();
        for(Definition d:definitions())canonical.append(d.name).append('|').append(d.argument).append('|').append(d.property).append('|').append(d.kind).append('|').append(d.min).append('|').append(d.max).append('|').append(new TreeSet<>(d.choices)).append('\n');
        try{
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(StandardCharsets.UTF_8));StringBuilder hex=new StringBuilder();
            for(byte b:digest)hex.append(String.format(Locale.ROOT,"%02x",b&255));return hex.toString();
        }catch(java.security.NoSuchAlgorithmException error){throw new IllegalStateException(error);}
    }

    static final class Entity {
        final String id,name;
        final List<String> aliases;
        final Set<String> capabilities;
        Entity(String id,String name,List<String> aliases,Set<String> capabilities){
            need(identifier(id),"ENTITY_ID");need(label(name),"ENTITY_NAME");
            need(aliases!=null&&aliases.size()<=16&&aliases.stream().allMatch(SemanticSkills::label),"ENTITY_ALIASES");
            need(capabilities!=null&&!capabilities.isEmpty()&&capabilities.size()<=REGISTRY.size(),"ENTITY_CAPABILITIES");
            for(String skill:capabilities)definition(skill);
            this.id=id;this.name=name;this.aliases=List.copyOf(aliases);this.capabilities=Set.copyOf(capabilities);
        }
    }
    static final class Catalog {
        final List<Entity> entities;
        private final Map<String,Entity> byId;
        Catalog(List<Entity> entities){
            need(entities!=null&&!entities.isEmpty()&&entities.size()<=128,"CATALOG_SIZE");
            Map<String,Entity> index=new LinkedHashMap<>();
            for(Entity entity:entities){need(entity!=null,"ENTITY_NULL");need(!index.containsKey(entity.id),"DUPLICATE_ENTITY");index.put(entity.id,entity);}
            this.entities=List.copyOf(entities);byId=Collections.unmodifiableMap(index);
        }
        Entity find(String id){Entity entity=byId.get(id);need(entity!=null,"UNKNOWN_ENTITY");return entity;}
        String resolve(String expression){
            need(label(expression),"ENTITY_EXPRESSION");String normalized=expression.trim().toLowerCase(Locale.ROOT);Set<String> matches=new LinkedHashSet<>();
            for(Entity entity:entities){
                if(entity.id.toLowerCase(Locale.ROOT).equals(normalized)||entity.name.trim().toLowerCase(Locale.ROOT).equals(normalized)||entity.aliases.stream().anyMatch(alias->alias.trim().toLowerCase(Locale.ROOT).equals(normalized)))matches.add(entity.id);
            }
            need(!matches.isEmpty(),"UNKNOWN_ENTITY");need(matches.size()==1,"AMBIGUOUS_ENTITY");return matches.iterator().next();
        }
    }
    static final class Call {
        final String skill,device;
        final Object value;
        Call(String skill,String device,Object value){this.skill=skill;this.device=device;this.value=value;}
        public boolean equals(Object other){if(!(other instanceof Call))return false;Call c=(Call)other;return Objects.equals(skill,c.skill)&&Objects.equals(device,c.device)&&Objects.equals(value,c.value);}
        public int hashCode(){return Objects.hash(skill,device,value);}
        String propertyKey(){return device+"."+definition(skill).property;}
    }
    static Call parse(String name,Map<String,?> args){
        Definition d=definition(name);need(args!=null&&args.keySet().equals(Set.of("device",d.argument)),"ARGUMENT_FIELDS");
        need(args.get("device") instanceof String&&identifier((String)args.get("device")),"ENTITY_ID");Object value=args.get(d.argument);d.validate(value);
        return new Call(name,(String)args.get("device"),value);
    }
    static final class Plan {
        final List<Call> calls;
        final Map<String,Object> goals;
        Plan(List<Call> calls,Map<String,Object> goals){this.calls=List.copyOf(calls);this.goals=Collections.unmodifiableMap(new LinkedHashMap<>(goals));}
    }
    static boolean allCallsSatisfied(List<Call> calls,Map<String,?> observed){
        need(calls!=null&&!calls.isEmpty()&&calls.size()<=MAX_CALLS&&observed!=null,"CALL_COUNT");
        // Do not use collapsed final goals: ordered on→off is not a no-op.
        for(Call call:calls){need(call!=null,"CALL_NULL");definition(call.skill).validate(call.value);}
        for(Call call:calls)if(!observed.containsKey(call.propertyKey())||!Objects.equals(call.value,observed.get(call.propertyKey())))return false;
        return true;
    }
    static Plan compile(Catalog catalog,List<Call> calls){
        need(catalog!=null,"CATALOG_NULL");need(calls!=null&&!calls.isEmpty()&&calls.size()<=MAX_CALLS,"CALL_COUNT");
        Map<String,Object> goals=new LinkedHashMap<>();
        for(Call call:calls){
            need(call!=null,"CALL_NULL");Definition d=definition(call.skill);Entity entity=catalog.find(call.device);
            need(entity.capabilities.contains(call.skill),"UNSUPPORTED_CAPABILITY");d.validate(call.value);goals.put(call.propertyKey(),call.value);
        }
        // Keep the complete ordered calls even when final goals collapse repeated assignments.
        return new Plan(calls,goals);
    }
}
