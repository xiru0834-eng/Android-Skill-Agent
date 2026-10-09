package edu.sydney.probe;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Runtime metadata only: never a Skill, entity catalog, binding or execution permission. */
final class DeviceContext {
    enum Kind { PHYSICAL_OR_UNKNOWN, EMULATOR_LIKELY }
    enum Orientation { UNDEFINED, PORTRAIT, LANDSCAPE }
    static final class Window {
        final int id,displayId,left,top,right,bottom;
        Window(int id,int displayId,int left,int top,int right,int bottom){
            need(id>=0,"WINDOW_ID");need(displayId>=0,"DISPLAY_ID");need(right>left&&bottom>top,"WINDOW_BOUNDS");
            this.id=id;this.displayId=displayId;this.left=left;this.top=top;this.right=right;this.bottom=bottom;
        }
    }
    final String deviceId,model,androidRelease,appPackage,appVersionName;
    final Kind kind;
    final Orientation orientation;
    final int screenWidth,screenHeight,densityDpi,rotation,androidApi;
    final double density,fontScale;
    final Double reportedXdpi,reportedYdpi;
    final long appVersionCode,capturedElapsedMs;
    final Window window;

    DeviceContext(String deviceId,Kind kind,String model,int width,int height,double density,int dpi,Double xdpi,Double ydpi,
                  double font,Orientation orientation,int rotation,int api,String release,String pkg,long code,String name,Window window,long clock){
        need(deviceId==null||deviceId.matches("[0-9a-f]{64}"),"AUDIT_ID");need(kind!=null,"KIND");
        need(width>0&&height>0,"SCREEN_SIZE");need(positive(density),"DENSITY");need(dpi>0,"DENSITY_DPI");
        need((xdpi==null||positive(xdpi))&&(ydpi==null||positive(ydpi)),"REPORTED_DPI");need(positive(font),"FONT_SCALE");
        need(orientation!=null,"ORIENTATION");need(rotation>=0&&rotation<=3,"ROTATION");need(api>=30,"ANDROID_API");
        need(pkg!=null&&pkg.length()<=160&&pkg.matches("[a-zA-Z0-9_]+(?:\\.[a-zA-Z0-9_]+)+"),"APP_PACKAGE");
        need(code>=0,"APP_VERSION");need(clock>=0,"CAPTURE_CLOCK");
        this.deviceId=deviceId;this.kind=kind;this.model=model;screenWidth=width;screenHeight=height;this.density=density;densityDpi=dpi;
        reportedXdpi=xdpi;reportedYdpi=ydpi;fontScale=font;this.orientation=orientation;this.rotation=rotation;androidApi=api;
        androidRelease=release;appPackage=pkg;appVersionCode=code;appVersionName=name;this.window=window;capturedElapsedMs=clock;
    }
    private static void need(boolean ok,String reason){if(!ok)throw new IllegalArgumentException(reason);}
    static boolean positive(double value){return Double.isFinite(value)&&value>0;}
    static String auditId(String androidId){
        if(androidId==null||androidId.isEmpty())return null;
        try{
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(("demo-probe-device-context-v1:"+androidId).getBytes(StandardCharsets.UTF_8));
            StringBuilder hex=new StringBuilder();for(byte b:digest)hex.append(String.format(Locale.ROOT,"%02x",b&255));return hex.toString();
        }catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException("SHA256_UNAVAILABLE",e);}
    }
    static Kind classify(String fingerprint,String model,String brand,String device,String product,String hardware){
        String fp=lower(fingerprint),m=lower(model),b=lower(brand),d=lower(device),p=lower(product),h=lower(hardware);
        boolean emulator=fp.startsWith("generic")||fp.startsWith("unknown")||m.contains("emulator")||m.contains("sdk_gphone")||m.contains("android sdk built for")
            ||(b.startsWith("generic")&&d.startsWith("generic"))||p.contains("sdk_gphone")||p.equals("sdk")||h.equals("goldfish")||h.equals("ranchu");
        return emulator?Kind.EMULATOR_LIKELY:Kind.PHYSICAL_OR_UNKNOWN;
    }
    private static String lower(String value){return value==null?"":value.toLowerCase(Locale.ROOT);}
}
