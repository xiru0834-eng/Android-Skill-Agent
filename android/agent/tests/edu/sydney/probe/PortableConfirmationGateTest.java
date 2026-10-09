package edu.sydney.probe;

public final class PortableConfirmationGateTest {
    private static void need(boolean value,String reason){if(!value)throw new AssertionError(reason);}
    public static void main(String[] args){
        var cancel=new PortableConfirmationGate();cancel.cancel();
        need(!cancel.dismiss(),"cancel must not launch");
        var negative=new PortableConfirmationGate();
        need(!negative.dismiss(),"negative or outside dismissal must not launch");
        negative.confirm();need(!negative.dismiss(),"late positive must not revive closed dialog");
        var positive=new PortableConfirmationGate();positive.confirm();positive.confirm();
        need(positive.dismiss(),"positive dismissal consumes launch");
        need(!positive.dismiss(),"duplicate dismissal must not launch twice");
        positive.confirm();need(!positive.dismiss(),"consumed launch cannot be revived");
        var revoked=new PortableConfirmationGate();revoked.confirm();revoked.cancel();
        need(!revoked.dismiss(),"cancel after positive must revoke pending launch");
        for(int n=0;n<100;n++){
            var gate=new PortableConfirmationGate();int launches=0;
            if(n%2==0)gate.confirm();else gate.cancel();
            for(int i=0;i<8;i++)if(gate.dismiss())launches++;
            need(launches==(n%2==0?1:0),"independent dialog has at most one launch");
        }
        System.out.println("PortableConfirmationGateTest: dismissal, cancellation, late/duplicate confirmation passed");
    }
}
