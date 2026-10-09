package edu.sydney.probe;

import java.util.List;

public final class DeploymentTest {
    private static final String A=ProbePolicy.TRANSFER_PACKAGE, B="edu.sydney.transferroom";
    private static final String W="11111111-1111-4111-8111-111111111111", V="22222222-2222-4222-8222-222222222222";
    private static TwoStepSkill source() { return new TwoStepSkill(List.of(new SwitchSkill(A,A+":id/mainToggle",false,true),new SwitchSkill(A,A+":id/otherToggle",false,true))); }
    private static DeploymentSkill skill(String workflow,String binding,String parent,List<String> roles,String pkg,List<String> ids) {
        return new DeploymentSkill(workflow,binding,parent,source(),roles,pkg,ids);
    }
    private static void reject(Runnable test) { try { test.run();throw new AssertionError("Accepted invalid deployment"); } catch(IllegalArgumentException expected) {} }
    public static void main(String[] args) {
        List<String> roles=List.of("Lighting","Ventilation"),ids=List.of(B+":id/ceiling",B+":id/airflow");
        DeploymentSkill s=skill(W,V,"",roles,B,ids);
        if(!s.source.appPackage.equals(A) || !s.boundSkill().appPackage.equals(B)) throw new AssertionError("Source overwritten");
        if(!s.boundSkill().steps.get(0).resourceId.equals(ids.get(0))) throw new AssertionError("Wrong binding");
        if(!s.boundSkill().steps.get(1).defaultDesired) throw new AssertionError("Lost workflow default");
        reject(()->skill("bad",V,"",roles,B,ids));
        reject(()->skill(W,V,V,roles,B,ids));
        reject(()->skill(W,V,"bad",roles,B,ids));
        reject(()->skill(W,V,"",List.of("Lighting","Lighting"),B,ids));
        reject(()->skill(W,V,"",List.of("Lighting"," lighting "),B,ids));
        reject(()->skill(W,V,"",List.of("","Fan"),B,ids));
        reject(()->skill(W,V,"",List.of("x\nApprove","Fan"),B,ids));
        reject(()->skill(W,V,"",roles,"com.private.app",ids));
        reject(()->skill(W,V,"",roles,B,List.of(ids.get(0),ids.get(0))));
        reject(()->skill(W,V,"",roles,B,List.of(A+":id/mainToggle",ids.get(1))));
        reject(()->skill(W,V,"",roles,B,List.of(ids.get(0))));
        BindingCatalog.Node one=new BindingCatalog.Node(ids.get(0),"Same name",true);
        BindingCatalog.Node two=new BindingCatalog.Node(ids.get(1),"Same name",true);
        if(BindingCatalog.select(B,List.of(one,two)).size()!=2) throw new AssertionError("Labels are not identity");
        if(!BindingCatalog.select(B,List.of(one,one)).isEmpty()) throw new AssertionError("Duplicate ID");
        if(!BindingCatalog.select(B,List.of(one,new BindingCatalog.Node(ids.get(0),"hidden duplicate",false))).isEmpty()) throw new AssertionError("Hidden duplicate");
        if(!BindingCatalog.select(B,List.of(new BindingCatalog.Node(A+":id/a","Foreign",true))).isEmpty()) throw new AssertionError("Foreign");
        if(!BindingCatalog.select(B,List.of(new BindingCatalog.Node(ids.get(0),"Disabled",false))).isEmpty()) throw new AssertionError("Unusable");
        System.out.println("DeploymentTest passed: source isolation, workflow defaults, mapping validation and candidate uniqueness");
    }
}
