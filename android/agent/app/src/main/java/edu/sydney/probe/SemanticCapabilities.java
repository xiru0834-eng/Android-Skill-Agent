package edu.sydney.probe;

import java.util.*;

/** Approved environment value domains, kept separate from reusable skill definitions. */
final class SemanticCapabilities {
    private static void need(boolean valid,String reason){if(!valid)throw new IllegalArgumentException(reason);}
    static final class Domain {
        final Set<Object> values;
        final Integer min,max,step;
        private Domain(Set<Object> values,Integer min,Integer max,Integer step){this.values=Set.copyOf(values);this.min=min;this.max=max;this.step=step;}
        static Domain values(List<?> values){
            need(values!=null&&!values.isEmpty()&&values.size()<=256&&values.stream().noneMatch(Objects::isNull),"DOMAIN_VALUES");
            Set<Object> unique=new HashSet<>(values);need(unique.size()==values.size(),"DOMAIN_VALUES");return new Domain(unique,null,null,null);
        }
        static Domain range(int min,int max,int step){
            need(min<=max&&step>0&&((long)max-min)%step==0,"DOMAIN_RANGE");return new Domain(Set.of(),min,max,step);
        }
        private void check(SemanticSkills.Definition definition){
            if(min!=null){need(definition.kind.equals("integer"),"DOMAIN_KIND");definition.validate(min);definition.validate(max);}
            else for(Object value:values)definition.validate(value);
        }
        boolean accepts(Object value){
            if(min==null)return values.contains(value);
            if(!(value instanceof Integer))return false;int number=(Integer)value;
            return number>=min&&number<=max&&((long)number-min)%step==0;
        }
    }
    static final class Environment {
        final String id;
        final Map<String,Map<String,Domain>> domains;
        Environment(String id,Map<String,Map<String,Domain>> domains){
            need(id!=null&&id.matches("[a-z][a-z0-9_]{0,63}"),"ENVIRONMENT_ID");
            need(domains!=null&&!domains.isEmpty()&&domains.size()<=128,"ENVIRONMENT_TARGETS");
            Map<String,Map<String,Domain>> copy=new LinkedHashMap<>();
            for(var target:domains.entrySet()){
                need(target.getKey()!=null&&target.getKey().matches("[a-z][a-z0-9_]{0,63}"),"ENTITY_ID");
                Map<String,Domain> capabilities=target.getValue();need(capabilities!=null&&!capabilities.isEmpty()&&capabilities.size()<=SemanticSkills.definitions().size(),"ENVIRONMENT_CAPABILITIES");
                for(var capability:capabilities.entrySet()){
                    var definition=SemanticSkills.definition(capability.getKey());need(capability.getValue()!=null,"DOMAIN_NULL");capability.getValue().check(definition);
                }
                copy.put(target.getKey(),Map.copyOf(capabilities));
            }
            this.id=id;this.domains=Collections.unmodifiableMap(copy);
        }
        void validate(SemanticSkills.Plan plan){
            for(var call:plan.calls){
                Map<String,Domain> capabilities=domains.get(call.device);need(capabilities!=null,"UNBOUND_ENTITY");
                Domain domain=capabilities.get(call.skill);need(domain!=null,"UNBOUND_CAPABILITY");need(domain.accepts(call.value),"UNSUPPORTED_VALUE");
            }
        }
    }
    static SemanticSkills.Plan compile(SemanticSkills.Catalog catalog,Environment environment,List<SemanticSkills.Call> calls){
        need(environment!=null,"ENVIRONMENT_NULL");var plan=SemanticSkills.compile(catalog,calls);environment.validate(plan);return plan;
    }
}
