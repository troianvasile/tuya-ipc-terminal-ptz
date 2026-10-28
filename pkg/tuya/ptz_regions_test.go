package tuya

import (
	"net/http"
	"testing"
)

func TestPTZTrustedRegions(t *testing.T) {
	for _, host := range []string{
		"protect-eu.ismartlife.me", "protect-we.ismartlife.me",
		"protect-us.ismartlife.me", "protect-ue.ismartlife.me",
		"protect.ismartlife.me", "protect-in.ismartlife.me",
	} {
		if !IsAllowedPTZHost(host) {
			t.Errorf("supported region host rejected: %s", host)
		}
	}
}

func TestPTZRejectsUntrustedHostsBeforeNetwork(t *testing.T) {
	bad := []string{
		"", "example.com", "protect-eu.ismartlife.me.evil.com",
		"protect-eu.ismartlife.me:443", "https://protect-eu.ismartlife.me",
		"PROTECT-EU.ISMARTLIFE.ME", "localhost", "127.0.0.1",
	}
	for _, host := range bad {
		if IsAllowedPTZHost(host) {
			t.Errorf("untrusted host accepted: %q", host)
		}
		if err := SendPTZ(&http.Client{}, host, "device-id", "UP", false); err == nil {
			t.Errorf("PTZ allowed untrusted host %q", host)
		}
	}
}

func TestPTZRejectsUnknownDirectionsBeforeNetwork(t *testing.T) {
	for _, dir := range []string{"DELETE", "STOP", "up", "../"} {
		if err := SendPTZ(&http.Client{}, "protect-eu.ismartlife.me", "device-id", dir, false); err == nil {
			t.Errorf("invalid direction allowed: %q", dir)
		}
	}
}
