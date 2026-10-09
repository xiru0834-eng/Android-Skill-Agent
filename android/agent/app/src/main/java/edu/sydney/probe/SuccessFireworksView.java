package edu.sydney.probe;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.os.SystemClock;
import android.view.View;

/** One short, silent burst. Touch and accessibility stay with the real controls. */
final class SuccessFireworksView extends View {
    private static final long DURATION_MS=900;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private long began;
    private boolean playing;
    private final Runnable finishBurst=()->{playing=false;setVisibility(GONE);};
    SuccessFireworksView(Context context){super(context);setClickable(false);setFocusable(false);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
    static boolean animationsEnabled(){return ValueAnimator.areAnimatorsEnabled();}
    void play(){if(!animationsEnabled())return;removeCallbacks(finishBurst);began=SystemClock.uptimeMillis();playing=true;setVisibility(VISIBLE);postDelayed(finishBurst,DURATION_MS);invalidate();}
    void stop(){removeCallbacks(finishBurst);playing=false;setVisibility(GONE);}
    boolean playing(){return playing;}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);if(!playing)return;if(!animationsEnabled()){stop();return;}
        float t=(SystemClock.uptimeMillis()-began)/(float)DURATION_MS;
        if(t>=1){playing=false;return;}
        float density=getResources().getDisplayMetrics().density;
        paint.setStrokeWidth(2*density);paint.setStrokeCap(Paint.Cap.ROUND);
        int[] colours={UiStyle.ACCENT,0xff63a781,0xffad7727};
        for(int burst=0;burst<3;burst++){
            float age=Math.max(0,(t-burst*.08f)/(1-burst*.08f));if(age<=0)continue;
            float distance=(1-(1-age)*(1-age))*Math.min(getHeight()*.44f,getWidth()*.19f);
            float cx=getWidth()*(.26f+burst*.24f),cy=getHeight()*(burst==1?.32f:.5f);
            paint.setColor(colours[burst]);paint.setAlpha((int)(210*(1-age)));
            for(int spark=0;spark<22;spark++){
                double angle=spark*Math.PI*2/22+burst*.2;
                float x=cx+(float)Math.cos(angle)*distance,y=cy+(float)Math.sin(angle)*distance+age*age*getHeight()*.2f;
                float tail=4*density*(1-age);
                canvas.drawLine(x,y,x-(float)Math.cos(angle)*tail,y-(float)Math.sin(angle)*tail,paint);
            }
        }
        postInvalidateOnAnimation();
    }
    @Override protected void onDetachedFromWindow(){removeCallbacks(finishBurst);playing=false;super.onDetachedFromWindow();}
}
