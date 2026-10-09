package edu.sydney.probe;
import java.io.*;
import java.nio.charset.StandardCharsets;
public final class UserLearningFilesTest {
    private static int tests;
    private static void need(boolean v){tests++;if(!v)throw new AssertionError();}
    private static void reject(Run r)throws Exception{tests++;try{r.run();throw new AssertionError();}catch(IOException expected){}}
    interface Run{void run()throws Exception;}
    public static void main(String[] args)throws Exception{
        byte[] large="a".repeat(300000).getBytes(StandardCharsets.UTF_8);
        need(UserLearningFiles.read(new ByteArrayInputStream(large),1048576).length()==300000);
        need(UserLearningFiles.read(new ByteArrayInputStream(new byte[]{97}),1).equals("a"));
        reject(()->UserLearningFiles.read(new ByteArrayInputStream(new byte[]{97,98}),1));
        reject(()->UserLearningFiles.read(null,1048576));
        reject(()->UserLearningFiles.read(new ByteArrayInputStream(large),0));
        reject(()->UserLearningFiles.read(new ByteArrayInputStream(large),1048577));
        reject(()->UserLearningFiles.read(new ByteArrayInputStream(new byte[]{(byte)0xc3}),1));
        reject(()->UserLearningFiles.read(new ByteArrayInputStream(large),1048576,()->{throw new IOException("CANCELLED_OR_LATE");}));
        var zero=new ByteArrayInputStream(new byte[]{97}){@Override public synchronized int read(byte[] b,int o,int l){return 0;}};
        need(UserLearningFiles.read(zero,1).equals("a"));
        need(UserLearningFiles.read(new ByteArrayInputStream("中文 / English".getBytes(StandardCharsets.UTF_8)),100).equals("中文 / English"));
        System.out.println("UserLearningFilesTest PASS "+tests+" bounded/UTF8/deadline checks; no Android/device proof");
    }
}
