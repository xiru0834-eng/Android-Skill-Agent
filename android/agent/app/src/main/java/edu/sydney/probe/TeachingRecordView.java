package edu.sydney.probe;
import org.json.*;

/** Read-only presentation of observed evidence. No completion or intent is invented. */
final class TeachingRecordView {
    static String[] ids(JSONObject trace){
        try{JSONArray steps=trace.getJSONArray("steps");
            String[] ids=new String[steps.length()];for(int i=0;i<ids.length;i++)ids[i]=steps.getJSONObject(i).getString("id");return ids;
        }catch(Exception e){return new String[]{"UNKNOWN"};}
    }
    static String actions(JSONObject trace,boolean en){
        StringBuilder out=new StringBuilder();
        try{JSONArray steps=trace.getJSONArray("steps");
            if(steps.length()==0)return en?"No actions were confirmed. No steps have been added automatically.":"还没有确认到操作，不会自动补写步骤。";
            for(int i=0;i<steps.length();i++){
                JSONObject step=steps.getJSONObject(i);String id=step.optString("id"),label;
                try{Boolean desired=id.equals("wfLampPower")||id.equals("wfFanPower")?step.getJSONObject("after").getJSONObject("values").getBoolean(id):null;label=TeachingText.observed(id,desired,step.getJSONObject("after").getString("page"),en);}
                catch(Exception e){label=en?"Action could not be described; see diagnostics":"操作无法解释，请查看技术详情";}
                if(i>0)out.append('\n');out.append(i+1).append(". ").append(label);
            }return out.toString();
        }catch(Exception e){return en?"Recording unavailable. See diagnostics.":"记录暂不可读，请查看技术详情。";}
    }
}
