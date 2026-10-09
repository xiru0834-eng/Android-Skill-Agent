package edu.sydney.probe;

/** Only an affirmative confirmation followed by dismissal can consume a launch. */
final class PortableConfirmationGate {
    private boolean confirmed,closed;
    void confirm(){if(!closed)confirmed=true;}
    void cancel(){closed=true;confirmed=false;}
    boolean dismiss(){
        if(closed)return false;
        closed=true;
        return confirmed;
    }
}
