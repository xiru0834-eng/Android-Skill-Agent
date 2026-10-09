package edu.sydney.probe;
import java.text.Normalizer;
import java.util.*;

/** Immutable additions only: no silent replacement of a name or evidence identity. */
final class NamedWorkflowPolicy {
    static String name(String input){
        if(input==null)throw new IllegalArgumentException("NAME_REQUIRED");
        String value=Normalizer.normalize(input.trim(),Normalizer.Form.NFC);
        if(SelectionText.blank(value)||value.length()>60||value.codePoints().anyMatch(c->Character.isISOControl(c)||Character.getType(c)==Character.FORMAT))
            throw new IllegalArgumentException("INVALID_NAME");
        return value;
    }
    static final class Entry {
        final String id,name,raw;
        Entry(String id,String name,String raw){
            if(id==null||!id.matches("[a-f0-9]{64}")||raw==null||raw.isBlank())throw new IllegalArgumentException("INVALID_ENTRY");
            this.id=id;this.name=name(name);this.raw=raw;
        }
    }
    static List<Entry> add(List<Entry> previous,Entry next){
        for(Entry old:previous){
            if(old.id.equals(next.id)){
                if(!old.raw.equals(next.raw)||!old.name.equals(next.name))throw new IllegalArgumentException("EVIDENCE_CONFLICT");
                return new ArrayList<>(previous);
            }
            if(old.name.toLowerCase(Locale.ROOT).equals(next.name.toLowerCase(Locale.ROOT)))throw new IllegalArgumentException("NAME_EXISTS");
        }
        if(previous.size()>=20)throw new IllegalArgumentException("LIBRARY_FULL");
        List<Entry> result=new ArrayList<>(previous);result.add(next);return result;
    }
}
