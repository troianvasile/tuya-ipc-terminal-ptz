package rtsp

import (
	"testing"
	"time"

	"github.com/pion/rtp"
)

func pcmuPacket(sequence uint16, timestamp uint32, samples int) *rtp.Packet {
	return &rtp.Packet{
		Header:  rtp.Header{SequenceNumber: sequence, Timestamp: timestamp, PayloadType: 0},
		Payload: make([]byte, samples),
	}
}

func TestTalkbackRTPClockIsContinuousAcrossSessions(t *testing.T) {
	clock := new(talkbackRTPClock)
	start := time.Unix(1_700_000_000, 0)

	first := pcmuPacket(0, 0, 320)
	out1 := clock.rewrite(first, start)
	if out1.SequenceNumber != 0 || out1.Timestamp != 0 {
		t.Fatalf("unexpected first RTP: seq=%d ts=%d", out1.SequenceNumber, out1.Timestamp)
	}

	second := clock.rewrite(pcmuPacket(1, 320, 320), start.Add(40*time.Millisecond))
	if second.SequenceNumber != 1 || second.Timestamp != 320 {
		t.Fatalf("unexpected continuous RTP: seq=%d ts=%d", second.SequenceNumber, second.Timestamp)
	}

	// A fresh RTSP microphone sender starts at 0 again three seconds later.
	newSource := pcmuPacket(0, 0, 320)
	third := clock.rewrite(newSource, start.Add(3040*time.Millisecond))
	if third.SequenceNumber != 2 || third.Timestamp != 24320 {
		t.Fatalf("RTP source reset leaked into outgoing track: seq=%d ts=%d", third.SequenceNumber, third.Timestamp)
	}
	if newSource.SequenceNumber != 0 || newSource.Timestamp != 0 {
		t.Fatal("source RTP packet was modified")
	}
}

func TestTalkbackRTPClockUsesPCMUFrameSize(t *testing.T) {
	clock := new(talkbackRTPClock)
	start := time.Unix(1_700_000_000, 0)
	_ = clock.rewrite(pcmuPacket(100, 1000, 160), start)
	second := clock.rewrite(pcmuPacket(101, 1160, 320), start.Add(20*time.Millisecond))
	third := clock.rewrite(pcmuPacket(102, 1480, 160), start.Add(60*time.Millisecond))
	if second.Timestamp != 1160 || third.Timestamp != 1480 {
		t.Fatalf("wrong timestamp progression: %d %d", second.Timestamp, third.Timestamp)
	}
}

func TestTalkbackRTPClockPacesOnePCMUFrame(t *testing.T) {
	clock := new(talkbackRTPClock)
	clock.pace(160)
	started := time.Now()
	clock.pace(160)
	if elapsed := time.Since(started); elapsed < 15*time.Millisecond {
		t.Fatalf("pacing elapsed %v, want approximately 20ms", elapsed)
	}
}

func TestTalkbackRTPClockSequenceWrapsNormally(t *testing.T) {
	clock := new(talkbackRTPClock)
	start := time.Unix(1_700_000_000, 0)
	_ = clock.rewrite(pcmuPacket(65535, 4294967200, 160), start)
	second := clock.rewrite(pcmuPacket(0, 64, 160), start.Add(20*time.Millisecond))
	if second.SequenceNumber != 0 || second.Timestamp != 64 {
		t.Fatalf("sequence/timestamp did not wrap: seq=%d ts=%d", second.SequenceNumber, second.Timestamp)
	}
}
