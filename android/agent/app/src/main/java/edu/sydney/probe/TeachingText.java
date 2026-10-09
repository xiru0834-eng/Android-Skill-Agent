package edu.sydney.probe;
/** Labels describe validated actions, never infer missing actions from free text. */
final class TeachingText {
    static String observed(String id,Boolean desired,String afterPage,boolean en){
        if(id.equals("wfLampSave")||id.equals("wfFanSave")||id.equals("wfLampCancel")||id.equals("wfFanCancel")){
            if(!afterPage.equals("single")&&!afterPage.equals("overview"))throw new IllegalArgumentException("UNKNOWN_AFTER_PAGE");
            boolean lamp=id.startsWith("wfLamp");
            String action=id.endsWith("Save")?(en?(lamp?"Save lamp settings":"Save fan settings"):(lamp?"保存灯的设置":"保存风扇设置"))
                :(en?(lamp?"Discard unsaved lamp changes":"Discard unsaved fan changes"):(lamp?"取消灯的未保存修改":"取消风扇的未保存修改"));
            return action+(afterPage.equals("single")?(en?"; stay on the single page":"；留在单页"):(en?"; return to overview":"；返回总览"));
        }
        return step(id,desired,en);
    }
    static String recordOrigin(String source,boolean en) {
        return source.equals("AUTOMATED")?(en?"Automated test record (not your new demonstration)":"自动化测试记录（不是你的新示范）")
            :(en?"Demonstration record (declared source)":"示范记录（来源为录制声明）");
    }
    static String recordState(String value,boolean en) {
        switch(value){
            case "STOPPED":return en?"Finished — review required":"示范已结束，待核对";
            case "CANCELLED":return en?"Cancelled — not a skill":"已取消，不会生成技能";
            case "REJECTED":return en?"Recording incomplete":"记录不完整";
            case "TIMED_OUT":return en?"Recording timed out":"录制超时";
            case "INTERRUPTED":case "RECORDING":return en?"Interrupted — record again":"记录中断，请重新示范";
            default:return en?"Record unavailable":"记录不可用";
        }
    }
    static String step(String id,Boolean desired,boolean en) {
        switch(id) {
            case "wfSingle":return en?"Switch to single-page controls":"切换到单页控制";
            case "wfMulti":return en?"Switch to overview / Pages":"切换到总览 / 三页模式";
            case "wfLampBack":case "wfFanBack":return en?"Return to overview":"返回总览";
            case "wfLampCancel":return en?"Cancel unsaved lamp changes":"取消灯的未保存修改";
            case "wfFanCancel":return en?"Cancel unsaved fan changes":"取消风扇的未保存修改";
            case "wfOpenLamp":return en?"Open reading lamp settings":"进入阅读灯设置";
            case "wfOpenFan":return en?"Open fan settings":"进入风扇设置";
            case "wfLampSave":return en?"Save lamp settings and return to the overview":"保存灯的设置，返回总览";
            case "wfFanSave":return en?"Save fan settings and return to the overview":"保存风扇设置，返回总览";
            case "wfLampPower":case "wfFanPower":
                if(desired==null)throw new IllegalArgumentException("MISSING_STATE");
                String device=id.contains("Lamp")?(en?"reading lamp":"阅读灯"):(en?"fan":"风扇");
                return en?"Set "+device+" to "+(desired?"ON":"OFF"):(desired?"打开":"关闭")+device;
        }
        for(int value:new int[]{20,40,60,80,100})if(id.equals("wfLampValue"+value))
            return en?"Set brightness to "+value+"%":"亮度设为 "+value+"%";
        for(int value=1;value<=3;value++)if(id.equals("wfFanValue"+value))
            return en?"Set fan speed to "+new String[]{"low","medium","high"}[value-1]:"风扇设为"+new String[]{"低档","中档","高档"}[value-1];
        throw new IllegalArgumentException("UNSUPPORTED_STEP");
    }
}
