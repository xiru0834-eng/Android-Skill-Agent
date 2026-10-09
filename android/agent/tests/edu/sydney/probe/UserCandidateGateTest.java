package edu.sydney.probe;
public final class UserCandidateGateTest {
    private static int n;
    private static void check(boolean x){n++;if(!x)throw new AssertionError("check "+n);}
    public static void main(String[] args){
        var a=new UserCandidateGate("snapshot",100);check(!a.claim("changed",101));check(!a.claim("snapshot",102));
        var b=new UserCandidateGate("snapshot",100);b.cancel();check(!b.claim("snapshot",101));
        var c=new UserCandidateGate("snapshot",100);check(!c.claim("snapshot",99));
        var d=new UserCandidateGate("snapshot",100);check(!d.claim("snapshot",120100));
        var e=new UserCandidateGate("snapshot",100);check(e.claim("snapshot",120099));check(!e.claim("snapshot",120099));
        System.out.println("UserCandidateGateTest PASS "+n+" single-use/snapshot/deadline checks; no Android proof");
    }
}
