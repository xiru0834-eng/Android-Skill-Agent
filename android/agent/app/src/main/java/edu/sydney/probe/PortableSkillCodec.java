package edu.sydney.probe;
import java.util.*;
import org.json.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Portable semantic catalog and environment binding. Never serializes local approval or device geometry. */
final class PortableSkillCodec {
    static final String PKG="edu.sydney.parameterroom",VERSION="0.8-parameter-room",PAGE="parameter_room";
    static final class Package {
        final String raw,hash,appVersion; final JSONArray catalog;
        final SemanticParameterCodec.Catalog semantics;final EnvironmentBinding.AppBinding binding;
        Package(String raw,String version,JSONArray catalog,Map<String,EnvironmentBinding.Target> targets)throws Exception {
            this.raw=raw;hash=hash(raw);appVersion=version;this.catalog=catalog;
            semantics=SemanticParameterCodec.catalog(catalog);binding=new EnvironmentBinding.AppBinding(PKG,targets);
        }
        SemanticSkills.Plan compile(JSONArray calls)throws Exception {
            return SemanticCapabilities.compile(semantics.entities,semantics.domains,SemanticParameterCodec.calls(calls));
        }
    }
    static String hash(String raw)throws Exception {
        StringBuilder h=new StringBuilder();for(byte b:MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8)))h.append(String.format(Locale.ROOT,"%02x",b&255));return h.toString();
    }
    static Package decode(String raw)throws Exception {
        WorkflowCodec.checkJson(raw,24000);JSONObject data=new JSONObject(raw);
        WorkflowCodec.fields(data,"schema","appPackage","appVersion","catalog","bindings");
        WorkflowCodec.require("portable_parameter_v1".equals(data.opt("schema"))&&PKG.equals(data.opt("appPackage")),"PACKAGE_SCOPE");
        WorkflowCodec.require(VERSION.equals(data.opt("appVersion")),"APP_VERSION");
        JSONArray catalog=data.getJSONArray("catalog");var semantic=SemanticParameterCodec.catalog(catalog);
        JSONObject rows=data.getJSONObject("bindings");Map<String,EnvironmentBinding.Target> targets=new LinkedHashMap<>();
        Set<String> keys=new HashSet<>();
        for(var entity:semantic.entities.entities)for(String skill:entity.capabilities){
            WorkflowCodec.require(Set.of("SetPower","SetBrightness","SetTemperature").contains(skill),"UNSUPPORTED_CAPABILITY");
            keys.add(entity.id+"."+SemanticSkills.definition(skill).property);
        }
        WorkflowCodec.require(rows.length()==keys.size(),"BINDING_COUNT");
        for(String key:keys){
            JSONObject r=rows.getJSONObject(key);WorkflowCodec.fields(r,"id","class","role","scope","page");
            for(String field:List.of("id","class","role","scope","page"))WorkflowCodec.require(r.opt(field) instanceof String,"BINDING_TYPE");
            String id=r.getString("id"),role=r.getString("role"),cls=r.getString("class");
            WorkflowCodec.require(id.matches("ps[A-Za-z0-9]{1,48}")&&Set.of("switch","slider").contains(role)
                &&cls.equals(role.equals("switch")?"android.widget.Switch":"android.widget.SeekBar")
                &&PAGE.equals(r.getString("page"))&&!r.getString("scope").isBlank(),"BINDING_CONTRACT");
            WorkflowCodec.require(key.endsWith(".power")==role.equals("switch"),"BINDING_ROLE");
            targets.put(key,new EnvironmentBinding.Target(key,PKG,id,"","",cls,role,r.getString("scope"),Set.of(PAGE)));
        }
        return new Package(raw,VERSION,catalog,targets);
    }
    static String template()throws Exception {
        JSONArray catalog=new JSONArray();JSONObject bindings=new JSONObject();
        catalog.put(entity("bedroom_light","Bedroom light",new String[]{"卧室灯","灯","light"},"SetBrightness","percent",0,100));
        catalog.put(entity("bedroom_ac","Bedroom air conditioner",new String[]{"卧室空调","空调","AC"},"SetTemperature","celsius",16,30));
        for(String[] row:new String[][]{{"bedroom_light.power","psLightPower","switch","Light"},{"bedroom_light.brightnessPercent","psBrightness","slider","Brightness"},
                {"bedroom_ac.power","psAcPower","switch","Air conditioner"},{"bedroom_ac.temperatureCelsius","psTemperature","slider","Temperature"}}){
            bindings.put(row[0],new JSONObject().put("id",row[1]).put("class",row[2].equals("switch")?"android.widget.Switch":"android.widget.SeekBar")
                .put("role",row[2]).put("scope",row[3]).put("page",PAGE));
        }
        String raw=new JSONObject().put("schema","portable_parameter_v1").put("appPackage",PKG).put("appVersion",VERSION).put("catalog",catalog).put("bindings",bindings).toString();
        decode(raw);return raw;
    }
    private static JSONObject entity(String id,String name,String[] aliases,String skill,String arg,int min,int max)throws Exception {
        return new JSONObject().put("device",id).put("name",name).put("aliases",new JSONArray(aliases)).put("capabilities",new JSONArray()
            .put(new JSONObject().put("skill","SetPower").put("domain",new JSONObject().put("values",new JSONArray(new String[]{"on","off"}))))
            .put(new JSONObject().put("skill",skill).put("domain",new JSONObject().put("min",min).put("max",max).put("step",1))));
    }
}
