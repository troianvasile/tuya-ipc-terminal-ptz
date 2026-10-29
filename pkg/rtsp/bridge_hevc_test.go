package rtsp

import (
	"encoding/binary"
	"io"
	"net"
	"strings"
	"testing"

	"github.com/pion/rtp"
	pion "github.com/pion/webrtc/v4"

	bridgewebrtc "tuya-ipc-terminal/pkg/webrtc"
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

func TestDataChannelPCMLAudioMatchesRTSPSDP(t *testing.T) {
	packet := &rtp.Packet{
		Header:  rtp.Header{PayloadType: 101},
		Payload: []byte{0, 0, 0xff, 0x7f, 0x00, 0x80},
	}

	normalizeDataChannelAudioPacket(packet, 101)

	if packet.PayloadType != 0 {
		t.Fatalf("payload type = %d, want 0", packet.PayloadType)
	}
	want := []byte{0xff, 0x80, 0x00}
	if string(packet.Payload) != string(want) {
		t.Fatalf("PCML converted to %x, want %x", packet.Payload, want)
	}
}

func TestHEVCBackchannelIsNegotiatedBeforeIncomingAudioTrack(t *testing.T) {
	api, err := bridgewebrtc.NewAPI()
	if err != nil {
		t.Fatalf("create WebRTC API: %v", err)
	}
	peerConnection, err := api.NewPeerConnection(pion.Configuration{})
	if err != nil {
		t.Fatalf("create peer connection: %v", err)
	}
	defer peerConnection.Close()

	bridge := &WebRTCBridge{peerConnection: peerConnection, audioCodecType: 101}
	if err := bridge.setupBackchannel(); err != nil {
		t.Fatalf("setup backchannel: %v", err)
	}
	if bridge.backchannel == nil {
		t.Fatal("backchannel was not created")
	}

	offer, err := peerConnection.CreateOffer(nil)
	if err != nil {
		t.Fatalf("create offer: %v", err)
	}
	if !strings.Contains(offer.SDP, "a=rtpmap:97 L16/8000") {
		t.Fatal("offer does not advertise L16/8000")
	}
}

func TestPCMUBackchannelIsTranscodedForPCMLCamera(t *testing.T) {
	packet := &rtp.Packet{
		Header:  rtp.Header{PayloadType: 0},
		Payload: []byte{0xff, 0x80},
	}

	normalizeBackchannelAudioPacket(packet, 101)

	if packet.PayloadType != 97 {
		t.Fatalf("payload type = %d, want 97", packet.PayloadType)
	}
	want := []byte{0x00, 0x00, 0x7c, 0x7d}
	if string(packet.Payload) != string(want) {
		t.Fatalf("PCMU converted to %x, want %x", packet.Payload, want)
	}
}
