package rtsp

import (
	"net"
	"testing"
)

func TestAddUDPClientUsesRTSPClientHostAndUpdatesDestination(t *testing.T) {
	forwarder := NewRTPForwarder()
	if err := forwarder.AddUDPClient("session", "127.0.0.2", 5000, 0); err != nil {
		t.Fatalf("add UDP client: %v", err)
	}
	defer forwarder.RemoveClient("session")

	client := forwarder.clients["session"]
	if !client.videoAddr.IP.Equal(net.ParseIP("127.0.0.2")) || client.videoAddr.Port != 5000 {
		t.Fatalf("video destination = %v, want 127.0.0.2:5000", client.videoAddr)
	}

	if err := forwarder.AddUDPClient("session", "127.0.0.3", 6000, 6002); err != nil {
		t.Fatalf("update UDP client: %v", err)
	}
	if !client.videoAddr.IP.Equal(net.ParseIP("127.0.0.3")) || client.videoAddr.Port != 6000 {
		t.Fatalf("updated video destination = %v, want 127.0.0.3:6000", client.videoAddr)
	}
	if !client.audioAddr.IP.Equal(net.ParseIP("127.0.0.3")) || client.audioAddr.Port != 6002 {
		t.Fatalf("audio destination = %v, want 127.0.0.3:6002", client.audioAddr)
	}
}

func TestUDPAddressRejectsInvalidClientDestination(t *testing.T) {
	for _, test := range []struct {
		host string
		port int
	}{{"", 5000}, {"127.0.0.1", 0}, {"127.0.0.1", 65536}} {
		if _, err := udpAddress(test.host, test.port); err == nil {
			t.Fatalf("udpAddress(%q, %d) unexpectedly succeeded", test.host, test.port)
		}
	}
}
