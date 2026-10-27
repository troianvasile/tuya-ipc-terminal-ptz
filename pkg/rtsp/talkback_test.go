package rtsp

import (
 "errors"
 "strings"
 "testing"
)

func TestTalkbackEnableOnceAndDisable(t *testing.T) {
 var calls []int
 var writes int
 c := &talkbackController{}
 enable := func(v int) error { calls = append(calls,v); return nil }
 for i:=0;i<3;i++ {
  if err:=c.forward(enable,func()error{writes++;return nil});err!=nil{t.Fatal(err)}
 }
 if writes!=3 || len(calls)!=1 || calls[0]!=1 { t.Fatalf("calls=%v writes=%d",calls,writes) }
 if err:=c.close(enable);err!=nil{t.Fatal(err)}
 if len(calls)!=2 || calls[1]!=0 { t.Fatalf("calls=%v",calls) }
 if err:=c.close(enable);err!=nil{t.Fatal(err)}
 if len(calls)!=2 { t.Fatalf("disable repeated: %v",calls) }
 if err:=c.forward(enable,func()error{return nil});err==nil {t.Fatal("expected closed error")}
}
func TestTalkbackEnableRetry(t *testing.T) {
 c:=&talkbackController{}
 attempts,writes:=0,0
 enable:=func(v int)error{attempts++; if attempts==1{return errors.New("mqtt offline")};return nil}
 send:=func()error{writes++;return nil}
 if err:=c.forward(enable,send);err==nil||!strings.Contains(err.Error(),"mqtt offline"){t.Fatalf("first: %v",err)}
 if err:=c.forward(enable,send);err!=nil{t.Fatal(err)}
 if attempts!=2||writes!=1{t.Fatalf("attempts=%d writes=%d",attempts,writes)}
}
func TestTalkbackWriteAndDisableErrors(t *testing.T) {
 c:=&talkbackController{}
 fn:=func(v int)error{if v==0{return errors.New("disable failed")};return nil}
 if err:=c.forward(fn,func()error{return errors.New("write failed")});err==nil||!strings.Contains(err.Error(),"write failed"){t.Fatalf("write: %v",err)}
 if err:=c.close(fn);err==nil||!strings.Contains(err.Error(),"disable failed"){t.Fatalf("close: %v",err)}
}
func TestTalkbackCloseBeforeUse(t *testing.T) {
 c:=&talkbackController{}
 count:=0
 if err:=c.close(func(int)error{count++;return nil});err!=nil{t.Fatal(err)}
 if count!=0{t.Fatal("speaker disabled before enabled")}
}
