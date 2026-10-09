package edu.sydney.probe;
import java.util.List;

public final class LanguageDecisionTest {
    public static void main(String[] args) {
        LanguageDecision d=new LanguageDecision("invoke","room_controls",true,null,"OK");
        if(!d.resolve(false,true).equals(List.of(true,true))) throw new AssertionError("Keep unmentioned fan");
        rejects(() -> new LanguageDecision("invoke","other",true,false,""));
        rejects(() -> new LanguageDecision("invoke","room_controls",null,null,""));
        rejects(() -> new LanguageDecision("clarify","room_controls",true,null,""));
        LanguageDecision q=new LanguageDecision("clarify","room_controls",null,null,"Which device?");
        rejects(() -> q.resolve(false,false));
        System.out.println("LanguageDecisionTest PASS");
    }
    private static void rejects(Runnable r) {
        try { r.run(); } catch(IllegalArgumentException expected) { return; }
        throw new AssertionError("Expected rejection");
    }
}
