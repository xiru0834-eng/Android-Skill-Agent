package edu.sydney.probe;
import java.io.*;
import java.nio.*;
import java.nio.charset.*;

/** New learning-material limit; does not widen any existing skill/import wire limit. */
final class UserLearningFiles {
    interface BeforeRead {void check()throws IOException;}
    static String read(InputStream in,int limit)throws IOException{return read(in,limit,()->{});}
    static String read(InputStream in,int limit,BeforeRead budget)throws IOException{
        if(in==null||limit<1||limit>1048576)throw new IOException("LEARNING_INPUT_LIMIT");
        var bytes=new ByteArrayOutputStream();byte[] buffer=new byte[4096];
        while(true){budget.check();int n=in.read(buffer,0,Math.min(buffer.length,limit-bytes.size()+1));if(n<0)break;
            if(n==0){budget.check();int b=in.read();if(b<0)break;bytes.write(b);}else bytes.write(buffer,0,n);
            if(bytes.size()>limit)throw new IOException("LEARNING_INPUT_LIMIT");
        }
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes.toByteArray())).toString();
    }
}
