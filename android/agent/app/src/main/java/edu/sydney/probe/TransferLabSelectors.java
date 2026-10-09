package edu.sydney.probe;
import java.util.*;

/** Explicit reviewed experiment-environment selectors; not part of Skill Schema. */
final class TransferLabSelectors {
    static final String PACKAGE="edu.sydney.transferlab";
    static final Set<String> PAGES=Set.of("single","overview","lamp","fan");
    static EnvironmentBinding.Target target(String id){
        String text="",role="text",scope="",cls="android.widget.TextView";Set<String> pages=PAGES;
        if(id.startsWith("wfOpen")){
            boolean lamp=id.equals("wfOpenLamp");
            EnvironmentBinding.need(lamp||id.equals("wfOpenFan"),"UNKNOWN_ENVIRONMENT_TARGET");
            text=lamp?"阅读灯 / Reading lamp →":"风扇 / Desk fan →";role="button";cls="android.widget.Button";pages=Set.of("overview");
        }else if(id.startsWith("wfLamp")||id.startsWith("wfFan")){
            boolean lamp=id.startsWith("wfLamp");String prefix=lamp?"wfLamp":"wfFan",suffix=id.substring(prefix.length());
            scope=lamp?"阅读灯 / Reading lamp":"风扇 / Desk fan";pages=Set.of("single",lamp?"lamp":"fan");
            if(suffix.equals("Power")){text="Power / 电源";role="switch";cls="android.widget.Switch";}
            else if(suffix.startsWith("Value")){
                String value=suffix.substring(5);List<String> values=lamp?List.of("20","40","60","80","100"):List.of("1","2","3");
                EnvironmentBinding.need(values.contains(value),"UNKNOWN_ENVIRONMENT_TARGET");
                text=lamp?value:List.of("低 Low","中 Mid","高 High").get(Integer.parseInt(value)-1);role="radio";cls="android.widget.RadioButton";
            }else if(List.of("Save","Cancel","Back").contains(suffix)){
                text=suffix.equals("Save")?"保存 Save":suffix.equals("Cancel")?"取消 Cancel":"返回 Back";role="button";cls="android.widget.Button";
            }else EnvironmentBinding.need(suffix.equals("Dirty"),"UNKNOWN_ENVIRONMENT_TARGET");
        }else if(id.equals("wfSingle")||id.equals("wfMulti")){
            text=id.equals("wfSingle")?"单页 Single":"三页 Pages";role="button";cls="android.widget.Button";pages=Set.of("single","overview");
        }else EnvironmentBinding.need(Set.of("wfPage","wfReady","wfOverallDirty","wfSummary").contains(id),"UNKNOWN_ENVIRONMENT_TARGET");
        // Dynamic observation labels have ID-only binding; no guessing from partial text.
        return new EnvironmentBinding.Target(id,PACKAGE,id,text,"",cls,role,scope,pages);
    }
}
