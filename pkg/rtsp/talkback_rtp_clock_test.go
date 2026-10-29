package rtsp

import (
	"testing"
	"time"

	"github.com/pion/rtp"
)

func TestTalkbackRTPClockStaysContinuousAcrossSources(t *testing.T) {
	clock := new(talkbackRTPClock)
	start := time.Unix(1_700_000_000, 0)
	first := &rtp.Packet{Header: rtp.Header{SequenceNumber: 10, Timestamp: 1000}, Payload: make([]byte, 160)}
	if got := clock.rewrite(first, start); got.SequenceNumber != 10 || got.Timestamp != 1000 {
		t.Fatalf("first packet = seq %d ts %d", got.SequenceNumber, got.Timestamp)
	}
	newSource := &rtp.Packet{Header: rtp.Header{SequenceNumber: 1, Timestamp: 1}, Payload: make([]byte, 160)}
	got := clock.rewrite(newSource, start.Add(20*time.Millisecond))
	if got.SequenceNumber != 11 || got.Timestamp != 1160 {
		t.Fatalf("clock reset: seq %d ts %d", got.SequenceNumber, got.Timestamp)
	}
	if newSource.SequenceNumber != 1 || newSource.Timestamp != 1 {
		t.Fatal("source packet was modified")
	}
}
