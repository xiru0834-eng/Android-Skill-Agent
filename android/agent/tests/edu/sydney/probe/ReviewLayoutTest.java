package edu.sydney.probe;
/** Content length must not push native approval controls beyond the window. */
public final class ReviewLayoutTest {
    static int checks;
    static void yes(boolean value){checks++;if(!value)throw new AssertionError("check "+checks);}
    public static void main(String[] args){
        for(int height:new int[]{320,480,720,1208,1920,2560})for(float density:new float[]{1,1.5f,3}){
            int content=ReviewLayout.guideHeightPx(height,density);
            yes(content>0&&content<=height/3&&content<=Math.round(280*density));
        }
        for(float density:new float[]{0,-1,Float.NaN,Float.POSITIVE_INFINITY}){
            try{ReviewLayout.guideHeightPx(720,density);throw new AssertionError("accepted invalid density");}
            catch(IllegalArgumentException expected){checks++;}
        }
        try{ReviewLayout.guideHeightPx(0,1);throw new AssertionError("accepted unavailable window");}
        catch(IllegalArgumentException expected){checks++;}
        System.out.println("ReviewLayoutTest: "+checks+" assertions passed");
    }
}
