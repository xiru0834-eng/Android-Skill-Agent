package edu.sydney.probe;

import java.util.Objects;

public final class DeviceContextTest {
    private static int checks;
    private static void eq(Object a,Object b){checks++;if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
    private static void rejects(String message,Runnable action){checks++;try{action.run();}catch(IllegalArgumentException e){eq(message,e.getMessage());return;}throw new AssertionError("accepted "+message);}
    private static final class Fixture {
        String id=DeviceContext.auditId("test-local-id"),model="test model",release="14",pkg="edu.sydney.transferlab",name="test";
        DeviceContext.Kind kind=DeviceContext.Kind.PHYSICAL_OR_UNKNOWN;
        int width=1080,height=2340,dpi=450,rotation=0,api=34;
        double density=2.8125,font=1;
        Double xdpi=420.0,ydpi=421.0;
        DeviceContext.Orientation orientation=DeviceContext.Orientation.PORTRAIT;
        long code=6,clock=500;
        DeviceContext.Window window=new DeviceContext.Window(12,0,0,80,1080,2260);
        DeviceContext make(){return new DeviceContext(id,kind,model,width,height,density,dpi,xdpi,ydpi,font,orientation,rotation,api,release,pkg,code,name,window,clock);}
    }
    public static void main(String[] args){
        String registry=SemanticSkills.registryHash();
        Fixture f=new Fixture();DeviceContext phone=f.make();
        eq(1080,phone.screenWidth);eq(2340,phone.screenHeight);eq(450,phone.densityDpi);eq(2.8125,phone.density);eq(1.0,phone.fontScale);
        eq(12,phone.window.id);eq(0,phone.window.displayId);eq(2180,phone.window.bottom-phone.window.top);
        f.width=720;f.height=1280;f.dpi=240;f.density=1.5;f.kind=DeviceContext.Kind.EMULATOR_LIKELY;f.id=DeviceContext.auditId("other-local-id");f.window=new DeviceContext.Window(21,0,0,40,720,1240);
        DeviceContext emulator=f.make();eq(720,emulator.screenWidth);eq(1280,emulator.screenHeight);eq(false,phone.deviceId.equals(emulator.deviceId));eq(1080,phone.screenWidth);eq(12,phone.window.id);
        f.width=1280;f.height=720;f.orientation=DeviceContext.Orientation.LANDSCAPE;f.rotation=1;eq(DeviceContext.Orientation.LANDSCAPE,f.make().orientation);
        f.orientation=DeviceContext.Orientation.UNDEFINED;f.window=null;f.id=null;f.xdpi=null;f.ydpi=null;eq(null,f.make().window);eq(null,f.make().deviceId);eq(null,f.make().reportedXdpi);
        eq(-50,new DeviceContext.Window(1,2,-50,-10,500,700).left);
        rejects("WINDOW_BOUNDS",()->new DeviceContext.Window(1,0,0,0,0,50));
        rejects("WINDOW_ID",()->new DeviceContext.Window(-1,0,0,0,20,30));
        rejects("DISPLAY_ID",()->new DeviceContext.Window(1,-1,0,0,20,30));
        f.width=0;rejects("SCREEN_SIZE",f::make);f.width=720;f.height=-1;rejects("SCREEN_SIZE",f::make);f.height=1280;
        for(double bad:new double[]{0,-1,Double.NaN,Double.POSITIVE_INFINITY}){f.density=bad;rejects("DENSITY",f::make);}f.density=1.5;
        f.dpi=0;rejects("DENSITY_DPI",f::make);f.dpi=240;
        for(double bad:new double[]{0,-1,Double.NaN,Double.NEGATIVE_INFINITY}){f.font=bad;rejects("FONT_SCALE",f::make);}f.font=1;
        f.xdpi=Double.NaN;rejects("REPORTED_DPI",f::make);f.xdpi=null;f.ydpi=-1.0;rejects("REPORTED_DPI",f::make);f.ydpi=null;
        f.rotation=4;rejects("ROTATION",f::make);f.rotation=-1;rejects("ROTATION",f::make);f.rotation=0;
        f.api=29;rejects("ANDROID_API",f::make);f.api=34;f.code=-1;rejects("APP_VERSION",f::make);f.code=6;
        f.clock=-1;rejects("CAPTURE_CLOCK",f::make);f.clock=500;
        f.id="raw-device-id";rejects("AUDIT_ID",f::make);f.id=null;
        f.pkg="";rejects("APP_PACKAGE",f::make);f.pkg="edu.sydney.transferlab";
        f.kind=null;rejects("KIND",f::make);f.kind=DeviceContext.Kind.PHYSICAL_OR_UNKNOWN;
        f.orientation=null;rejects("ORIENTATION",f::make);f.orientation=DeviceContext.Orientation.UNDEFINED;
        eq(null,DeviceContext.auditId(null));eq(null,DeviceContext.auditId(""));eq(DeviceContext.auditId("abc"),DeviceContext.auditId("abc"));eq(64,DeviceContext.auditId("abc").length());
        eq(DeviceContext.Kind.EMULATOR_LIKELY,DeviceContext.classify("generic/test","sdk_gphone","google","generic","sdk_gphone","ranchu"));
        eq(DeviceContext.Kind.EMULATOR_LIKELY,DeviceContext.classify("GENERIC/test","test","test","test","test","test"));
        eq(DeviceContext.Kind.PHYSICAL_OR_UNKNOWN,DeviceContext.classify("samsung/test","SM-S916B","samsung","dm2q","dm2q","qcom"));
        eq(DeviceContext.Kind.PHYSICAL_OR_UNKNOWN,DeviceContext.classify(null,null,null,null,null,null));
        eq(registry,SemanticSkills.registryHash());eq("SetBrightness",SemanticSkills.definition("SetBrightness").name);eq("percent",SemanticSkills.definition("SetBrightness").argument);
        System.out.println("DeviceContextTest PASS "+checks+" checks");
    }
}
