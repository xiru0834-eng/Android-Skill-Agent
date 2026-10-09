package edu.sydney.probe;

/** Presentation only. ENDED is a local completeness check, not compiler approval. */
final class TeachingStatus {
    static final class Data {
        boolean connected,selected,active,ready,pending,inspecting,busy,draft,saved,running,savedOverview,preparing;
        String end="",error="";int steps;
        boolean routeValid=true,flexible;
    }
    static String kind(Data d){
        if(d.preparing)return "PREPARING";
        if(d.running)return "RUNNING";
        if(d.active)return !d.ready?"PREPARING":d.pending?"CONFIRMING":d.inspecting?"INSPECTING":"RECORDING";
        if(d.busy)return "GENERATING";
        if(!d.selected)return d.connected?"IDLE":"DISCONNECTED";
        if(d.saved)return "SAVED";
        if(d.draft)return "REVIEW";
        if("CANCELLED".equals(d.end))return "CANCELLED";
        if(!d.error.isEmpty())return "ERROR";
        if("STOPPED".equals(d.end))return (d.flexible?d.steps>0:d.steps==4||d.steps==8)&&d.savedOverview&&d.routeValid?"ENDED":"INCOMPLETE";
        return "ERROR";
    }
    static String title(String k,boolean en){
        switch(k){
            case "IDLE":return en?"Ready to teach":"尚未开始录制";
            case "DISCONNECTED":return en?"Service disconnected":"暂时不能录制";
            case "PREPARING":return en?"Preparing — please wait":"正在准备，请稍等";
            case "RECORDING":return en?"● Recording":"● 正在录制";
            case "CONFIRMING":return en?"Recording · confirming action":"录制中 · 正在确认操作";
            case "INSPECTING":return en?"Recording · return to Pages":"录制中 · 请返回三页模式";
            case "ENDED":return en?"Recording ended · ready to review":"录制已结束 · 可以整理指南";
            case "INCOMPLETE":return en?"Recording ended · incomplete":"录制已结束 · 记录不完整";
            case "CANCELLED":return en?"Recording cancelled":"已取消本次录制";
            case "GENERATING":return en?"Generating your guide":"正在整理操作指南";
            case "REVIEW":return en?"Guide ready · check each step":"指南已生成 · 请核对";
            case "SAVED":return en?"Skill saved":"技能已保存";
            case "RUNNING":return en?"Running the reviewed skill":"正在执行已审核技能";
            default:return en?"Recording stopped · needs attention":"录制已停止 · 需要检查";
        }
    }
    static String hint(String k,String error,int steps,boolean en){
        switch(k){
            case "IDLE":return en?"Name your task, then tap Start recording. Your saved skill is kept.":"填写任务，点击“开始录制”。已有技能不会被替换。";
            case "DISCONNECTED":return en?"Connect Demo Probe in Accessibility settings before recording.":"请先在无障碍设置里连接 Demo Probe 服务。";
            case "PREPARING":return en?"Opening the experiment. Do not tap until Recording appears.":"正在打开实验界面，看到“正在录制”后再操作。";
            case "RECORDING":return en?"Perform your task. Tap Finish recording when done.":"可以操作了。完成后，点下方“结束录制”。";
            case "CONFIRMING":return en?"Wait for this action to be confirmed before the next tap.":"刚才的操作还未确认，请稍等再进行下一步。";
            case "INSPECTING":return en?"Only viewing is supported here. Switch back to Pages to continue.":"当前单页只支持查看，切回“三页 Pages”再继续录制。";
            case "ENDED":return en?"Recording kept ("+steps+" steps). Generate and review the guide. No skill saved yet.":"已保留 "+steps+" 步记录。下一步整理并核对指南；尚未保存技能。";
            case "INCOMPLETE":return en?"Kept "+steps+" steps. Check confirmed actions and saved targets; see details.":"已保留 "+steps+" 步。请检查操作是否确认、修改是否保存；详情中可查看失败位置。";
            case "CANCELLED":return en?"Stopped. This recording will not become a skill. Your saved skill is unchanged.":"已经停止，本次记录不会生成技能。已有技能不变。";
            case "GENERATING":return en?"Keep this page open. Nothing will execute or be saved automatically.":"请留在此页等待，不会自动执行或保存技能。";
            case "REVIEW":return en?"Check the guide matches your intent, then choose Review & save.":"检查每一步是否符合你的意图，确认后再保存。";
            case "SAVED":return en?"Saved does not mean executed. Run it explicitly when ready.":"保存不等于执行成功。准备好后可主动执行验证。";
            case "RUNNING":return en?"You can stop at any time. Completion requires target verification.":"随时可以停止；只有核验目标后才会报告完成。";
            default:return error(error,en);
        }
    }
    static String error(String code,boolean en){
        if(code.equals("TIMED_OUT"))return en?"The recording time budget was reached. Evidence kept; review budgets or record again.":"已达到录制时间预算。已有记录保留，可检查预算设置或重新录制。";
        if(code.startsWith("OVERLAPPING_INPUT"))return en?"A second tap arrived before the previous action was confirmed. Evidence kept; record again and wait for confirmation.":"上一个操作还未确认就收到了下一次点击。记录已保留；重录时等提示确认再操作。";
        if(code.startsWith("OBSERVATION_TIMEOUT"))return en?"Could not confirm the last action. Recording stopped; evidence kept.":"未能确认刚才的操作结果，录制已停止，已有记录保留。";
        if(code.contains("SINGLE_PAGE")||code.contains("LAYOUT"))return en?"This recorder supports the three-page route. Return to Pages and record again.":"目前只支持三页流程录制。请切回“三页 Pages”后重新示范。";
        if(code.equals("START_NOT_OVERVIEW")||code.equals("CLICK_BEFORE_BASELINE"))return en?"Start at a saved overview or single page; wait for Recording before tapping.":"请从已保存的总览或单页开始，等出现“正在录制”后再点击。";
        if(code.equals("LEFT_ALLOWED_APPS"))return en?"Left the experiment. Recording stopped; no other apps are recorded.":"已离开实验应用，录制已停止，不记录其他应用。";
        if(code.equals("INCOMPLETE_STOP"))return en?"Stopped before the last state was confirmed. Evidence kept; not ready to generate.":"停止时最后的状态还未确认。记录已保留，暂不能整理成技能。";
        return en?"Could not verify this recording. Evidence kept; check details or record again.":"这次记录未通过检查，已有记录保留。可查看详情或重新录制。";
    }
    static boolean canGenerate(String kind){return "ENDED".equals(kind);}
    static boolean canStart(Data d){return d.connected&&!d.active&&!d.busy&&!d.running&&!d.preparing;}
    static String clock(long millis){long seconds=Math.max(0,millis)/1000;return String.format(java.util.Locale.ROOT,"%02d:%02d",seconds/60,seconds%60);}
}
