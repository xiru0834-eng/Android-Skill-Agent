package edu.sydney.probe;

/** Parameter bridge text boundary, independent of model transport and UI. */
final class ParameterText {
    static String checked(String raw){
        String text=SelectionText.checked(raw);
        if(text.length()>240)throw new IllegalArgumentException("TEXT_TOO_LONG");
        if(text.codePoints().anyMatch(c->c<32))throw new IllegalArgumentException("INVALID_TEXT");
        return text;
    }
    static final class Snapshot {
        final String text;
        private final String original;
        Snapshot(String raw){text=checked(raw);original=raw;}
        boolean current(String raw){return original.equals(raw);}
    }
}
