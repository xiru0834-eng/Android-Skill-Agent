package edu.sydney.probe;

/** Dynamic launch geometry only; never grants authority to a node or changes Skill semantics. */
final class PortableLaunchViewport {
    static boolean inside(int left,int top,int right,int bottom,int viewLeft,int viewTop,int viewRight,int viewBottom) {
        return right>left && bottom>top && viewRight>viewLeft && viewBottom>viewTop
            && left>=viewLeft && top>=viewTop && right<=viewRight && bottom<=viewBottom;
    }
}
