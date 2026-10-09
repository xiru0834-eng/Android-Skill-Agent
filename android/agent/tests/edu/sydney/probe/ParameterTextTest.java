package edu.sydney.probe;

import java.util.*;

public final class ParameterTextTest {
    private static int checks;
    private static void eq(Object expected,Object actual){checks++;if(!Objects.equals(expected,actual))throw new AssertionError(expected+" != "+actual);}
    private static void rejects(String reason,Runnable action){checks++;try{action.run();}catch(IllegalArgumentException error){eq(reason,error.getMessage());return;}throw new AssertionError("Accepted "+reason);}
    public static void main(String[] args){
        for(String raw:List.of("  Set bedroom light to 80 percent  ","  把卧室灯调到80%  ","Set fan to speed 2","开灯")){
            var snapshot=new ParameterText.Snapshot(raw);
            eq(raw.trim(),snapshot.text);eq(true,snapshot.current(raw));
            eq(false,snapshot.current(raw+" "));eq(false,snapshot.current(raw+" changed"));eq(false,snapshot.current(null));
        }
        for(String unit:List.of("a","灯")){
            eq(unit.repeat(240),ParameterText.checked(unit.repeat(240)));
            rejects("TEXT_TOO_LONG",()->ParameterText.checked(unit.repeat(241)));
            eq(unit.repeat(240),ParameterText.checked(" "+unit.repeat(240)+" "));
        }
        String emoji="\uD83D\uDE00";
        eq(emoji.repeat(120),ParameterText.checked(emoji.repeat(120)));
        rejects("TEXT_TOO_LONG",()->ParameterText.checked(emoji.repeat(121)));
        for(String control:List.of("\n","\r","\t","\0"))rejects("INVALID_TEXT",()->ParameterText.checked("light"+control+"on"));
        rejects("EMPTY_TEXT",()->ParameterText.checked(null));
        for(String empty:List.of("","   ","　","\u00A0","\u0085"))rejects("EMPTY_TEXT",()->ParameterText.checked(empty));
        for(String broken:List.of("\uD800","\uDC00","\uD800x"))rejects("INVALID_TEXT",()->ParameterText.checked(broken));
        // Unrelated workflow-selection clients retain their existing 500 boundary.
        eq("a".repeat(500),SelectionText.checked("a".repeat(500)));
        var snapshot=new ParameterText.Snapshot("  Set fan to speed 2 ");
        eq(false,snapshot.current(snapshot.text));eq(true,snapshot.current("  Set fan to speed 2 "));
        System.out.println("ParameterTextTest passed: "+checks+" checks; exact raw snapshot and bridge-aligned text; no model calls");
    }
}
