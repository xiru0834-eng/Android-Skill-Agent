package edu.sydney.probe;

/** Validate the raw value before any trim/normalization; never shorten intent. */
final class TeachingInput {
    private static String checked(String raw,int limit,String field){
        if(SelectionText.blank(raw))throw new IllegalArgumentException(field+"_REQUIRED");
        if(raw.length()>limit)throw new IllegalArgumentException(field+"_LENGTH");
        for(int i=0;i<raw.length();i++){
            char c=raw.charAt(i);
            if(Character.isHighSurrogate(c)){
                if(i+1>=raw.length()||!Character.isLowSurrogate(raw.charAt(++i)))throw new IllegalArgumentException(field+"_UNICODE");
            }else if(Character.isLowSurrogate(c))throw new IllegalArgumentException(field+"_UNICODE");
            else if(Character.isISOControl(c)&&!(field.equals("GOAL")&&(c=='\n'||c=='\r'||c=='\t')))
                throw new IllegalArgumentException(field+"_CHARACTER");
        }
        return raw.trim();
    }
    static String name(String raw){return NamedWorkflowPolicy.name(checked(raw,60,"NAME"));}
    static String goal(String raw){return checked(raw,240,"GOAL");}
}
