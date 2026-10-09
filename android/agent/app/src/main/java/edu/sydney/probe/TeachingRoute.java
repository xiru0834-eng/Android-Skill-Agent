package edu.sydney.probe;

/** Hints for the existing fixed protocol, not free-text intent inference. */
final class TeachingRoute {
    static boolean valid(String[] ids){
        if(ids==null||ids.length>8)return false;
        if(ids.length==0)return true;
        String first="wfOpenLamp".equals(ids[0])?"Lamp":"wfOpenFan".equals(ids[0])?"Fan":null;
        if(first==null)return false;
        for(int i=0;i<ids.length;i++){
            String group=i<4?first:first.equals("Lamp")?"Fan":"Lamp";String id=ids[i];
            if(id==null)return false;
            switch(i%4){
                case 0:if(!id.equals("wfOpen"+group))return false;break;
                case 1:if(!id.equals("wf"+group+"Power"))return false;break;
                case 2:if(!id.matches(group.equals("Lamp")?"wfLampValue(20|40|60|80|100)":"wfFanValue[123]"))return false;break;
                case 3:if(!id.equals("wf"+group+"Save"))return false;break;
            }
        }return true;
    }
    static boolean complete(String[] ids){return valid(ids)&&(ids.length==4||ids.length==8);}
    static String next(String[] ids,boolean en){
        if(!valid(ids))return en?"This sequence is outside the supported route. Finish and review the record.":"当前顺序不符合支持的流程，请结束并查看记录。";
        if(ids.length==8)return en?"All eight steps recorded. Tap Finish recording.":"八步已记录，可以点“结束录制”了。";
        if(ids.length==0)return en?"Next: open lamp or fan settings.":"下一步：进入阅读灯或风扇设置。";
        String first=ids[0].equals("wfOpenLamp")?"Lamp":"Fan";
        String group=ids.length<4?first:first.equals("Lamp")?"Fan":"Lamp";
        boolean lamp=group.equals("Lamp");
        if(ids.length==4)return en?"One device saved. Finish now to keep the other unchanged, or open "+(lamp?"lamp":"fan")+" settings to include it.":"一组已保存。可以结束录制，另一设备保持不变；或继续进入"+(lamp?"阅读灯设置":"风扇设置")+"。";
        switch(ids.length%4){
            case 0:return en?"Next: open "+(lamp?"lamp":"fan")+" settings.":"下一步：进入"+(lamp?"阅读灯":"风扇")+"设置。";
            case 1:return en?"Next: change "+(lamp?"lamp":"fan")+" power to demonstrate your target.":"下一步：切换"+(lamp?"灯开关":"风扇开关")+"到要示范的状态。";
            case 2:return en?"Next: choose a different "+(lamp?"brightness":"fan speed")+" as your target.":"下一步：选择与当前不同的"+(lamp?"亮度":"档位")+"作为目标。";
            default:return en?"Next: tap Save to return to overview.":"下一步：点“保存 Save”，返回总览。";
        }
    }
}
