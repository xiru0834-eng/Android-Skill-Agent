package edu.sydney.probe;

import org.json.*;
import java.util.TreeSet;

/** One-way audit encoding. There is deliberately no import/write-back-to-Skill operation. */
final class DeviceContextCodec {
    private static Object value(Object v){return v==null?JSONObject.NULL:v;}
    static JSONObject encode(DeviceContext c)throws JSONException{
        JSONObject window=c.window==null?null:new JSONObject().put("id",c.window.id).put("displayId",c.window.displayId)
            .put("bounds",new JSONArray().put(c.window.left).put(c.window.top).put(c.window.right).put(c.window.bottom));
        return new JSONObject().put("schemaVersion",1).put("deviceId",value(c.deviceId)).put("deviceIdSource","SHA256_SCOPED_ANDROID_ID_NOT_ADB_SERIAL")
            .put("deviceKind",c.kind.name()).put("kindEvidence","BUILD_HEURISTIC_NOT_ATTESTATION").put("model",value(c.model))
            .put("screenWidth",c.screenWidth).put("screenHeight",c.screenHeight).put("screenSource","MAXIMUM_WINDOW_METRICS_LOGICAL_PX_NOT_PANEL_RESOLUTION")
            .put("density",c.density).put("densityDpi",c.densityDpi).put("reportedXdpi",value(c.reportedXdpi)).put("reportedYdpi",value(c.reportedYdpi))
            .put("fontScale",c.fontScale).put("orientation",c.orientation.name()).put("rotation",c.rotation)
            .put("androidApi",c.androidApi).put("androidRelease",value(c.androidRelease)).put("appPackage",c.appPackage)
            .put("appVersionCode",c.appVersionCode).put("appVersionName",value(c.appVersionName)).put("currentWindow",value(window)).put("capturedElapsedMs",c.capturedElapsedMs);
    }
    static JSONObject registryReceipt()throws JSONException{
        JSONArray definitions=new JSONArray();
        for(SemanticSkills.Definition d:SemanticSkills.definitions()){
            JSONArray choices=new JSONArray();for(String choice:new TreeSet<>(d.choices))choices.put(choice);
            definitions.put(new JSONObject().put("id",d.name).put("entityArgument","device").put("valueArgument",d.argument)
                .put("property",d.property).put("kind",d.kind).put("min",d.min).put("max",d.max).put("choices",choices));
        }
        return new JSONObject().put("source","SemanticSkills.definitions").put("registrySha256",SemanticSkills.registryHash()).put("definitions",definitions);
    }
}
