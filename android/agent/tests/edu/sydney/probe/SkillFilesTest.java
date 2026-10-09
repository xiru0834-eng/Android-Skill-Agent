package edu.sydney.probe;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class SkillFilesTest {
    public static void main(String[] args) throws Exception {
        String unicode = "{\"test\":\"演示\"}";
        if (!unicode.equals(SkillFiles.read(new ByteArrayInputStream(unicode.getBytes(StandardCharsets.UTF_8)))))
            throw new AssertionError("UTF-8 roundtrip");
        if (SkillFiles.read(new ByteArrayInputStream(new byte[8192])).length() != 8192)
            throw new AssertionError("exact boundary");
        reject(new byte[8193]);
        if(SkillFiles.read(new ByteArrayInputStream(new byte[9000]),262144).length()!=9000)
            throw new AssertionError("new workflow size");
        try{SkillFiles.read(new ByteArrayInputStream(new byte[262145]),262144);throw new AssertionError("unbounded workflow file");}
        catch(IOException expected){}
        reject(new byte[]{(byte)0xc3, 0x28});
        reject(new byte[]{(byte)0xe4, (byte)0xb8});
        System.out.println("SkillFilesTest passed: UTF-8, byte cap, malformed and truncated encoding");
    }
    private static void reject(byte[] input) throws Exception {
        try { SkillFiles.read(new ByteArrayInputStream(input)); throw new AssertionError("accepted invalid bytes"); }
        catch (IOException expected) { }
    }
}
