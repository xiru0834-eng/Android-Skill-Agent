package edu.sydney.probe;

/** Raw-input boundaries: never infer intent from a shortened prefix. */
public final class TeachingInputTest {
    private static int checks;
    private static void ok(boolean value){checks++;if(!value)throw new AssertionError("check "+checks);}
    private static void bad(Runnable task){try{task.run();throw new AssertionError("invalid metadata accepted");}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args){
        ok(TeachingInput.name("  阅读模式  ").equals("阅读模式"));
        ok(TeachingInput.name("e\u0301").equals("é"));
        ok(TeachingInput.name("x".repeat(60)).length()==60);
        ok(TeachingInput.name("😀".repeat(30)).length()==60);
        bad(()->TeachingInput.name("x".repeat(60)+"NO"));
        bad(()->TeachingInput.name("😀".repeat(31)));
        bad(()->TeachingInput.name(null));bad(()->TeachingInput.name(" "));
        bad(()->TeachingInput.name("x\nname"));bad(()->TeachingInput.name("x\u200bname"));
        bad(()->TeachingInput.name("x\ud800"));bad(()->TeachingInput.name("x\udc00"));
        ok(TeachingInput.goal(" 开灯\nSet brightness to 60%. ").equals("开灯\nSet brightness to 60%."));
        ok(TeachingInput.goal("x".repeat(240)).length()==240);
        ok(TeachingInput.goal("😀".repeat(120)).length()==240);
        bad(()->TeachingInput.goal("x".repeat(240)+" do not execute"));
        bad(()->TeachingInput.goal("😀".repeat(121)));
        bad(()->TeachingInput.goal(null));bad(()->TeachingInput.goal("\t\n"));
        bad(()->TeachingInput.goal("x\u0000"));bad(()->TeachingInput.goal("x\ud800"));
        System.out.println("PASS TeachingInputTest: "+checks+" raw UTF-16 / Unicode / bilingual metadata checks");
    }
}
