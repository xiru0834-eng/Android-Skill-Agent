package edu.sydney.probe;
public final class PortableWindowReadPolicyTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("window read policy");}
    public static void main(String[] args){
        need(PortableWindowReadPolicy.failure(false,0,0).equals("NO_TREE"));
        need(PortableWindowReadPolicy.failure(false,2,1).equals("NO_TREE"));
        need(PortableWindowReadPolicy.failure(false,2,0).equals("STALE_WINDOWS"));
        need(PortableWindowReadPolicy.failure(true,2,0).equals(""));
        need(PortableWindowReadPolicy.failure(false,-1,0).equals("NO_TREE"));
        need(PortableWindowReadPolicy.failure(false,2,1,false).equals("STALE_WINDOWS"));
        need(PortableWindowReadPolicy.failure(false,2,1,true).equals("NO_TREE"));
        need(PortableWindowReadPolicy.foreign(7,true,2,true));
        need(PortableWindowReadPolicy.foreign(7,false,1,false));
        need(!PortableWindowReadPolicy.foreign(7,true,1,false));
        need(!PortableWindowReadPolicy.foreign(-1,false,2,true));
        System.out.println("PortableWindowReadPolicyTest: 7 checks passed");
    }
}
