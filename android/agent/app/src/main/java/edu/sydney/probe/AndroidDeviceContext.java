package edu.sydney.probe;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.res.Configuration;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.DisplayMetrics;
import android.view.Display;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import org.json.*;

/** Reads public SDK metadata at a run boundary, never traverses other Apps or changes display settings. */
final class AndroidDeviceContext {
    static JSONObject capture(ProbeService service,String targetPackage){
        long started=SystemClock.elapsedRealtime();JSONArray issues=new JSONArray();
        AccessibilityNodeInfo root=null;AccessibilityWindowInfo window=null;
        try{
            int displayId=Display.DEFAULT_DISPLAY;DeviceContext.Window currentWindow=null;
            root=service.getRootInActiveWindow();
            if(root!=null&&targetPackage.contentEquals(root.getPackageName()==null?"":root.getPackageName())){
                window=root.getWindow();
                if(window!=null){
                    Rect b=new Rect();window.getBoundsInScreen(b);displayId=window.getDisplayId();
                    currentWindow=new DeviceContext.Window(window.getId(),displayId,b.left,b.top,b.right,b.bottom);
                }else issues.put("TARGET_WINDOW_UNAVAILABLE");
            }else issues.put("TARGET_WINDOW_UNAVAILABLE");
            Display display=service.getSystemService(DisplayManager.class).getDisplay(displayId);
            if(display==null)throw new IllegalStateException("DISPLAY_UNAVAILABLE");
            // API 30+: display context first, then window context. No actual overlay is created.
            Context context=service.createDisplayContext(display).createWindowContext(WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,null);
            Rect maximum=context.getSystemService(WindowManager.class).getMaximumWindowMetrics().getBounds();
            DisplayMetrics metrics=context.getResources().getDisplayMetrics();Configuration config=context.getResources().getConfiguration();
            PackageInfo app=service.getPackageManager().getPackageInfo(targetPackage,0);
            String id=DeviceContext.auditId(Settings.Secure.getString(service.getContentResolver(),Settings.Secure.ANDROID_ID));
            if(id==null)issues.put("SCOPED_DEVICE_ID_UNAVAILABLE");
            Double xdpi=DeviceContext.positive(metrics.xdpi)?(double)metrics.xdpi:null,ydpi=DeviceContext.positive(metrics.ydpi)?(double)metrics.ydpi:null;
            if(xdpi==null||ydpi==null)issues.put("REPORTED_PHYSICAL_DPI_UNAVAILABLE");
            DeviceContext.Orientation orientation=config.orientation==Configuration.ORIENTATION_PORTRAIT?DeviceContext.Orientation.PORTRAIT:
                config.orientation==Configuration.ORIENTATION_LANDSCAPE?DeviceContext.Orientation.LANDSCAPE:DeviceContext.Orientation.UNDEFINED;
            DeviceContext snapshot=new DeviceContext(id,DeviceContext.classify(Build.FINGERPRINT,Build.MODEL,Build.BRAND,Build.DEVICE,Build.PRODUCT,Build.HARDWARE),
                Build.MODEL,maximum.width(),maximum.height(),metrics.density,metrics.densityDpi,xdpi,ydpi,config.fontScale,orientation,display.getRotation(),
                Build.VERSION.SDK_INT,Build.VERSION.RELEASE,targetPackage,app.getLongVersionCode(),app.versionName,currentWindow,SystemClock.elapsedRealtime());
            return new JSONObject().put("status",issues.length()==0?"AVAILABLE":"PARTIAL").put("issues",issues)
                .put("snapshot",DeviceContextCodec.encode(snapshot)).put("captureDurationMs",SystemClock.elapsedRealtime()-started)
                .put("source","BOUND_PROBE_SERVICE_PUBLIC_SDK").put("callerPackage",service.getPackageName()).put("processUid",android.os.Process.myUid());
        }catch(Exception error){
            // Diagnostic failure neither invents defaults nor alters existing execution authority.
            try{return new JSONObject().put("status","UNAVAILABLE").put("issues",issues.put("CONTEXT_CAPTURE_FAILED:"+error.getClass().getSimpleName()))
                .put("snapshot",JSONObject.NULL).put("captureDurationMs",SystemClock.elapsedRealtime()-started);}
            catch(JSONException impossible){throw new IllegalStateException("DEVICE_CONTEXT_AUDIT_FAILED",impossible);}
        }finally{if(window!=null)window.recycle();if(root!=null)root.recycle();}
    }
}
