package edu.sydney.probe;
import org.json.*;
final class TeachingGuide {
    static String render(String raw,boolean en) {
        return render(raw,en,WorkflowResources.defaults());
    }
    static String render(String raw,boolean en,WorkflowResources resources) {
        try {
            JSONObject skill=WorkflowCodec.decode(raw);StringBuilder text=new StringBuilder();
            text.append(en?"Observed operation guide\n\n":"根据实际记录整理的操作指南\n\n");
            text.append(en?"Recorded goal: ":"本次记录的目标：").append(skill.getString("goal")).append("\n\n");
            JSONArray steps=skill.getJSONArray("steps");
            for(int i=0;i<steps.length();i++) {
                JSONObject step=steps.getJSONObject(i);
                String label=TeachingText.step(step.getString("id"),step.isNull("desired")?null:step.getBoolean("desired"),en);
                if(skill.getInt("version")==3)label=TeachingText.observed(step.getString("id"),step.isNull("desired")?null:step.getBoolean("desired"),step.getString("afterPage"),en);
                text.append(i+1).append(". ").append(label).append('\n');
            }
            JSONArray g=skill.getJSONArray("finalGoals");
            text.append(en?"\nCompletion conditions\n":"\n最终完成条件\n");
            text.append(goals(g,en));
            if(skill.getInt("version")==3)text.append(en?"\nAll requested targets must be saved; untouched fields keep their initial values. No unsaved changes.\n":"\n所有目标须已保存，未涉及字段保持初态，且不存在未保存修改。\n");
            else text.append(en?"\nBoth settings must be saved together, with no unsaved changes.\n":"\n两项设置须同时保存，且不存在未保存的修改。\n");
            if(skill.getInt("version")==3)text.append(en?"Ordered process; intermediate states are retained. Start at: ":"有序流程，保留中间状态。起始页面：").append(skill.getString("startPage"))
                .append(en?"; finish at: ":"；结束页面：").append(skill.getString("endPage"))
                .append(en?"; execution budget: ":"；执行总预算：").append(resources.runMs(steps.length())/1000.0).append(en?" s\n":" 秒\n");
            text.append("AUTOMATED".equals(skill.getString("source"))?(en?"Source: automated test demonstration":"来源：自动化测试示范"):(en?"Source: user-declared demonstration":"来源：用户声明的手动示范"));
            text.append(en?"\nSaved does not mean verified on this or another device.":"\n保存不等于已通过本机或跨设备验证。");
            return text.toString();
        }catch(JSONException e){throw new IllegalArgumentException("INVALID_GUIDE",e);}
    }
    static String goals(JSONArray g,boolean en)throws JSONException {
        String lamp=(g.isNull(0)?(en?"Lamp power: keep initial":"灯电源：保持初态"):TeachingText.step("wfLampPower",g.getInt(0)==1,en))+" · "+
            (g.isNull(1)?(en?"brightness: keep initial":"亮度：保持初态"):g.getInt(1)+"%");
        String fan=(g.isNull(2)?(en?"Fan power: keep initial":"风扇电源：保持初态"):TeachingText.step("wfFanPower",g.getInt(2)==1,en))+" · "+
            (g.isNull(3)?(en?"speed: keep initial":"档位：保持初态"):TeachingText.step("wfFanValue"+g.getInt(3),true,en));
        return lamp+"\n"+fan;
    }
}
