package edu.sydney.probe;
/** Bound review prose, not the recorded skill or the approval controls. */
final class ReviewLayout {
    private ReviewLayout(){}
    static int guideHeightPx(int availableHeight,float density){
        if(availableHeight<3||!Float.isFinite(density)||density<=0)throw new IllegalArgumentException("UNAVAILABLE_REVIEW_WINDOW");
        return Math.max(1,Math.min(availableHeight/3,Math.round(280*density)));
    }
}
