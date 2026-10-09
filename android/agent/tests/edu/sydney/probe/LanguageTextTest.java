package edu.sydney.probe;
public final class LanguageTextTest {
    public static void main(String[] args) {
        check(LanguageText.message("已核验完成 / Verified complete",true),"Verified complete");
        check(LanguageText.message("未执行 / No action: BRIDGE_HTTP_401",false),"未执行 (BRIDGE_HTTP_401)");
        check(LanguageText.message("请问要打开什么？",true),"请问要打开什么？");
        check(LanguageText.targets("阅读灯 / Lamp: 开启 / ON\n风扇 / Fan: 保持不变 / Keep",true),"Lamp: ON\nFan: Keep");
        check(LanguageText.targets("阅读灯 / Lamp: 关闭 / OFF",false),"阅读灯: 关闭");
        System.out.println("LanguageTextTest PASS");
    }
    private static void check(String actual,String expected) { if(!actual.equals(expected)) throw new AssertionError(actual); }
}
