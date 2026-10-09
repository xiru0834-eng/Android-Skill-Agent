package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import org.json.*;
import java.util.*;

/** Data-only v2 contract checks. No phone inputs, model calls or user approvals. */
public final class SemanticWireChecks extends Instrumentation {
    private int checks;
    interface Check {void run()throws Exception;}
    private void ok(boolean yes,String name){if(!yes)throw new AssertionError(name);checks++;}
    private void bad(Check test,String name)throws Exception {boolean rejected=false;try{test.run();}catch(IllegalArgumentException expected){rejected=true;}ok(rejected,name);}
    private JSONArray catalog()throws Exception {
        JSONArray rows=new JSONArray();Object[] values={"on",80,24,2,60,"cool",50,4000};int index=0;
        for(var definition:SemanticSkills.definitions()){
            rows.put(new JSONObject().put("device","entity_"+index).put("name","设备 "+index).put("aliases",new JSONArray())
                .put("capabilities",new JSONArray().put(new JSONObject().put("skill",definition.name)
                    .put("domain",new JSONObject().put("values",new JSONArray().put(values[index]))))));index++;
        }return rows;
    }
    private JSONObject call(String skill,String device,String key,Object value)throws Exception {
        return new JSONObject().put("skill",skill).put("args",new JSONObject().put("device",device).put(key,value));
    }
    private JSONObject response(JSONArray calls)throws Exception {
        return new JSONObject().put("request_id","wire").put("status","invoke").put("calls",calls).put("message","Review / 请确认");
    }
    @Override public void onCreate(Bundle args){super.onCreate(args);start();}
    @Override public void onStart(){Bundle out=new Bundle();try{
        JSONArray catalog=catalog();ok(SemanticParameterCodec.catalog(catalog).entities.entities.size()==8,"eight dynamic entities");
        Object[] values={"on",80,24,2,60,"cool",50,4000};JSONArray calls=new JSONArray();int index=0;
        for(var definition:SemanticSkills.definitions())calls.put(call(definition.name,"entity_"+index,definition.argument,values[index++]));
        ok(SemanticParameterCodec.response(response(calls).toString(),"wire",catalog).getJSONArray("calls").length()==8,"eight ordered actions");
        bad(()->SemanticParameterCodec.response(response(calls).toString(),"other",catalog),"wrong request ID");
        JSONArray invalid=new JSONArray(calls.toString()).put(call("SetBrightness","ghost","percent",80));
        bad(()->SemanticParameterCodec.response(response(invalid).toString(),"wire",catalog),"invalid last call rejects whole list");
        for(Object value:List.of("80",true,55,-1,101)){
            JSONArray wrong=new JSONArray().put(call("SetBrightness","entity_1","percent",value));
            bad(()->SemanticParameterCodec.response(response(wrong).toString(),"wire",catalog),"strict brightness "+value);
        }
        bad(()->SemanticParameterCodec.response(response(new JSONArray().put(calls.getJSONObject(1))).toString()
            .replace("\"percent\":80","\"percent\":80.0"),"wire",catalog),"literal JSON floating point rejected");
        for(String status:List.of("clarify","reject")){
            ok(SemanticParameterCodec.response(response(new JSONArray()).put("status",status).toString(),"wire",catalog).getJSONArray("calls").length()==0,"empty "+status);
            bad(()->SemanticParameterCodec.response(response(calls).put("status",status).toString(),"wire",catalog),"no calls on "+status);
        }
        JSONObject domain=catalog.getJSONObject(2).getJSONArray("capabilities").getJSONObject(0);
        domain.put("domain",new JSONObject().put("min",16).put("max",30).put("step",3));
        bad(()->SemanticParameterCodec.catalog(catalog),"step endpoint invalid");
        domain.put("domain",new JSONObject().put("min",16).put("max",30).put("step",2));
        ok(SemanticParameterCodec.response(response(calls).toString(),"wire",catalog).getJSONArray("calls").length()==8,"range domain");
        JSONArray wrong=new JSONArray().put(call("SetTemperature","entity_2","celsius",25));
        bad(()->SemanticParameterCodec.response(response(wrong).toString(),"wire",catalog),"step mismatch");
        JSONArray many=new JSONArray();for(int n=0;n<32;n++)many.put(calls.getJSONObject(1));
        ok(SemanticParameterCodec.response(response(many).toString(),"wire",catalog).getJSONArray("calls").length()==32,"32 ordered calls");
        many.put(calls.getJSONObject(1));bad(()->SemanticParameterCodec.response(response(many).toString(),"wire",catalog),"33 resource cap");
        JSONObject extra=new JSONObject(catalog.getJSONObject(0).toString()).put("approved",true);
        bad(()->SemanticParameterCodec.catalog(new JSONArray().put(extra)),"catalog is not approval");
        ok(SemanticParameterCodec.text("灯".repeat(2000),2000).length()==2000,"2000 unicode text");
        for(String value:List.of("", " ","灯".repeat(2001),"x\u007f", "\uD800"))bad(()->SemanticParameterCodec.text(value,2000),"invalid wire text");
        out.putString("summary","PASS SemanticWireChecks checks="+checks+"; GUI runs=0; model calls=0");finish(-1,out);
    }catch(Throwable error){out.putString("error",error.getClass().getSimpleName()+": "+error.getMessage());finish(1,out);}}
}
