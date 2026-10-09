package edu.sydney.probe;
public final class SelectionTextTest {
    private static void check(boolean yes){if(!yes)throw new AssertionError();}
    private static void deny(String text){try{SelectionText.checked(text);throw new AssertionError();}catch(IllegalArgumentException expected){}}
    public static void main(String[] args){
        check(SelectionText.checked("  Run Reading60.  ").equals("Run Reading60."));
        check(SelectionText.checked("a".repeat(499)).length()==499);
        check(SelectionText.checked("a".repeat(500)).length()==500);
        deny("a".repeat(501));deny("a".repeat(501)+" DO NOT EXECUTE.");
        check(SelectionText.checked("😀".repeat(250)).length()==500);deny("😀".repeat(251));
        deny(null);deny("");deny("   ");deny("\ud800");deny("\udc00");
        check(SelectionText.checked("请执行阅读60，风扇保持低档。").contains("阅读60"));
        System.out.println("SelectionTextTest: 13 boundary checks passed");
    }
}
