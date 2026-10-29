package rtsp

import (
	"testing"

	"github.com/pion/rtp"
)

func TestPCMuRTPToPCMAPreservesRTPClock(t *testing.T) {
	input := &rtp.Packet{
		Header:  rtp.Header{PayloadType: 0, SequenceNumber: 31, Timestamp: 8000},
		Payload: []byte{0xff, 0x7f},
	}

	output := pcmuRTPToPCMA(input)

	if output.PayloadType != 8 {
		t.Fatalf("payload type = %d, want 8", output.PayloadType)
	}
	if output.SequenceNumber != input.SequenceNumber || output.Timestamp != input.Timestamp {
		t.Fatalf("RTP clock changed: got sequence %d timestamp %d", output.SequenceNumber, output.Timestamp)
	}
	if output.Payload[0] != 0xd5 || output.Payload[1] != 0xd5 {
		t.Fatalf("silence conversion = %x, want d5 d5", output.Payload)
	}
	if input.Payload[0] != 0xff || input.Payload[1] != 0x7f {
		t.Fatalf("input payload was modified: %x", input.Payload)
	}
}
