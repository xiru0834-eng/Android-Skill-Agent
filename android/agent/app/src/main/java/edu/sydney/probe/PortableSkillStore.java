package edu.sydney.probe;
import android.content.Context;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Local approval is deliberately not part of the exported package. */
final class PortableSkillStore {
    private final Context context;
    PortableSkillStore(Context context){this.context=context;}
    void version()throws Exception {WorkflowCodec.require(PortableSkillCodec.VERSION.equals(context.getPackageManager().getPackageInfo(PortableSkillCodec.PKG,0).versionName),"APP_VERSION");}
    String incoming()throws Exception {try(var f=context.openFileInput("portable-incoming.json")){return SkillFiles.read(f,24000);}}
    void approve(String raw)throws Exception {
        var pkg=PortableSkillCodec.decode(raw);version();
        write("portable-approved.json",pkg.raw);
        WorkflowCodec.require(context.getSharedPreferences("portable_approval",0).edit().putString("hash",pkg.hash).commit(),"APPROVAL_STORAGE");
    }
    PortableSkillCodec.Package approved()throws Exception {
        String raw;try(var f=context.openFileInput("portable-approved.json")){raw=SkillFiles.read(f,24000);}
        catch(FileNotFoundException missing){throw new IllegalArgumentException("LOCAL_REVIEW_REQUIRED");}
        var pkg=PortableSkillCodec.decode(raw);version();
        WorkflowCodec.require(pkg.hash.equals(context.getSharedPreferences("portable_approval",0).getString("hash","")),"LOCAL_REVIEW_REQUIRED");return pkg;
    }
    void write(String name,String raw)throws Exception {
        if(!java.util.Set.of("portable-approved.json","portable-result.json").contains(name))throw new IllegalArgumentException("FILE_SCOPE");
        var file=new android.util.AtomicFile(new File(context.getFilesDir(),name));FileOutputStream stream=null;
        try{stream=file.startWrite();stream.write(raw.getBytes(StandardCharsets.UTF_8));file.finishWrite(stream);}
        catch(Exception error){if(stream!=null)file.failWrite(stream);throw error;}
    }
}
