package edu.sydney.probe;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Bounded bytes, strict UTF-8. Closing the provider stream belongs to the caller. */
public final class SkillFiles {
    public static final int MAX_BYTES = 8192;
    private SkillFiles() {}
    public static String read(InputStream stream) throws IOException {
        return read(stream,MAX_BYTES);
    }
    public static String read(InputStream stream,int limit) throws IOException {
        if(limit<=0||limit>262144)throw new IOException("Invalid file limit");
        if (stream == null) throw new IOException("No stream");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        for (int count; (count = stream.read(buffer)) != -1;) {
            if (count == 0) {
                int single = stream.read();
                if (single == -1) break;
                bytes.write(single);
            } else bytes.write(buffer, 0, count);
            if (bytes.size() > limit) throw new IOException("File exceeds byte limit: "+limit);
        }
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes.toByteArray())).toString();
    }
}
