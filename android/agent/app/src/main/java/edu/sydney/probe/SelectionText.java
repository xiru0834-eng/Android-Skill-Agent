package edu.sydney.probe;

/** Same UTF-16 boundary as the bridge; never truncate a command to make it valid. */
final class SelectionText {
    /** Match the bridge's Unicode blank-input boundary, not ASCII trim alone. */
    static boolean blank(String value) {
        return value == null || value.codePoints().allMatch(c ->
                Character.isWhitespace(c) || Character.isSpaceChar(c) || c == 0x85);
    }
    static String checked(String raw) {
        if (raw == null) throw new IllegalArgumentException("EMPTY_TEXT");
        if (raw.length() > 500) throw new IllegalArgumentException("TEXT_TOO_LONG");
        for (int i = 0; i < raw.length(); i++) {
            char value = raw.charAt(i);
            if (Character.isHighSurrogate(value)) {
                if (++i >= raw.length() || !Character.isLowSurrogate(raw.charAt(i)))
                    throw new IllegalArgumentException("INVALID_TEXT");
            } else if (Character.isLowSurrogate(value)) {
                throw new IllegalArgumentException("INVALID_TEXT");
            }
        }
        String text = raw.trim();
        if (blank(text)) throw new IllegalArgumentException("EMPTY_TEXT");
        return text;
    }
}
