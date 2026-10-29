package rtsp

import (
	"encoding/binary"
	"io"
	"net"
	"testing"

	"github.com/pion/rtp"
)

func TestDataChannelHEVCVideoPayloadTypeMatchesRTSPSDP(t *testing.T) {
	bridge := &WebRTCBridge{rtpForwarder: NewRTPForwarder()}
	bridge.rtpForwarder.videoSSRC = 42

	server, client := net.Pipe()
	defer server.Close()
	defer client.Close()
	if err := bridge.rtpForwarder.AddTCPClient("test", server, 0, 2, 4); err != nil {
		t.Fatalf("add TCP client: %v", err)
	}
	defer bridge.rtpForwarder.RemoveClient("test")

	done := make(chan struct{})
	go func() {
		bridge.forwardDataChannelPacket(&rtp.Packet{
			Header:  rtp.Header{SSRC: 42, PayloadType: 95},
			Payload: []byte{1, 2, 3},
		})
		close(done)
	}()

	interleaved := make([]byte, 4)
	if _, err := io.ReadFull(client, interleaved); err != nil {
		t.Fatalf("read interleaved header: %v", err)
	}
	if interleaved[0] != '$' || interleaved[1] != 0 {
		t.Fatalf("unexpected interleaved header: %v", interleaved)
	}
	raw := make([]byte, binary.BigEndian.Uint16(interleaved[2:]))
	if _, err := io.ReadFull(client, raw); err != nil {
		t.Fatalf("read RTP packet: %v", err)
	}
	var forwarded rtp.Packet
	if err := forwarded.Unmarshal(raw); err != nil {
		t.Fatalf("unmarshal forwarded RTP: %v", err)
	}
	if forwarded.PayloadType != 96 {
		t.Fatalf("payload type = %d, want 96", forwarded.PayloadType)
	}
	<-done
}
