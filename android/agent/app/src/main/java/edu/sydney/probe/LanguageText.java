package edu.sydney.probe;

/** Localizes our fixed dual-language labels; model explanations remain verbatim. */
public final class LanguageText {
    private LanguageText() {}
    public static String message(String text,boolean english) {
        String[] parts=text.split(" / ",2);
        if(parts.length<2) return text;
        if(english) return parts[1];
        String en=parts[1];int colon=en.lastIndexOf(": ");
        return parts[0]+(colon>=0?" ("+en.substring(colon+2)+")":"");
    }
    public static String targets(String text,boolean english) {
        if(text.isEmpty()) return text;
        StringBuilder result=new StringBuilder();
        for(String line:text.split("\n")) {
            String[] p=line.split(" / ");
            if(result.length()>0)result.append('\n');
            if(p.length!=3 || !p[1].contains(": ")) { result.append(line);continue; }
            String[] label=p[1].split(": ",2);
            result.append(english?label[0]:p[0]).append(": ").append(english?p[2]:label[1]);
        }
        return result.toString();
    }
}
