package edu.sydney.probe;
public final class TeachingRouteTest {
    static void yes(boolean b){if(!b)throw new AssertionError();}
    public static void main(String[] args){
        String[] lamp={"wfOpenLamp","wfLampPower","wfLampValue60","wfLampSave","wfOpenFan","wfFanPower","wfFanValue1","wfFanSave"};
        String[] fan={"wfOpenFan","wfFanPower","wfFanValue3","wfFanSave","wfOpenLamp","wfLampPower","wfLampValue20","wfLampSave"};
        for(String[] route:new String[][]{lamp,fan})for(int n=0;n<=8;n++){
            String[] prefix=java.util.Arrays.copyOf(route,n);yes(TeachingRoute.valid(prefix));yes(TeachingRoute.complete(prefix)==(n==4||n==8));
            yes(!TeachingRoute.next(prefix,false).isBlank());yes(!TeachingRoute.next(prefix,true).isBlank());
            String[] expected=route==lamp?new String[]{"设置","灯开关","亮度","保存","风扇设置","风扇开关","档位","保存","结束录制"}:new String[]{"设置","风扇开关","档位","保存","阅读灯设置","灯开关","亮度","保存","结束录制"};
            yes(TeachingRoute.next(prefix,false).contains(expected[n]));
        }
        for(int brightness:new int[]{20,40,60,80,100})for(int speed:new int[]{1,2,3}){String[] variant=lamp.clone();variant[2]="wfLampValue"+brightness;variant[6]="wfFanValue"+speed;yes(TeachingRoute.complete(variant));}
        yes(!TeachingRoute.valid(null));yes(!TeachingRoute.complete(null));
        yes(TeachingRoute.next(lamp,false).contains("结束录制"));
        yes(TeachingRoute.next(new String[]{"wfOpenFan"},false).contains("风扇开关"));
        for(String[] bad:new String[][]{{"wfLampPower"},{"wfOpenLamp","wfFanPower"},{"wfOpenLamp","wfLampPower","wfLampValue10"},{"wfOpenLamp","wfLampPower","wfLampValue60","wfLampSave","wfOpenLamp"},java.util.Arrays.copyOf(lamp,9)}){
            yes(!TeachingRoute.valid(bad));yes(!TeachingRoute.complete(bad));yes(TeachingRoute.next(bad,false).contains("不符合"));
        }
        System.out.println("TeachingRouteTest PASS: both orders, all prefixes, malformed paths, bilingual hints");
    }
}
