package tuya

import (
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
)

type ptzRoundTrip func(*http.Request) (*http.Response, error)

func (f ptzRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestSendPTZ(t *testing.T) {
	for _, tc := range []struct {
		name, direction               string
		stop                          bool
		response                      string
		httpStatus                    int
		wantPath, wantBody, wantError string
	}{
		{name: "start", direction: "LEFT", response: `{"success":true}`, wantPath: "/api/jarvis/ptz/start", wantBody: `"direction":"LEFT"`},
		{name: "stop", stop: true, response: `{"success":true}`, wantPath: "/api/jarvis/ptz/end", wantBody: `"devId":"camera-1"`},
		{name: "denied", direction: "RIGHT", response: `{"success":false,"errorMsg":"No access"}`, wantPath: "/api/jarvis/ptz/start", wantError: "No access"},
		{name: "server error", direction: "UP", response: `{}`, httpStatus: 503, wantPath: "/api/jarvis/ptz/start", wantError: "503"},
		{name: "bad json", direction: "DOWN", response: `broken`, wantPath: "/api/jarvis/ptz/start", wantError: "invalid PTZ response"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			client := &http.Client{Transport: ptzRoundTrip(func(r *http.Request) (*http.Response, error) {
				if r.Method != http.MethodPost || r.URL.Host != "protect-eu.ismartlife.me" || r.URL.Path != tc.wantPath {
					t.Errorf("unexpected request: %v", r.URL)
				}
				if r.Header.Get("Origin") != "https://protect-eu.ismartlife.me" {
					t.Errorf("missing origin")
				}
				body, _ := io.ReadAll(r.Body)
				if tc.wantBody != "" && !strings.Contains(string(body), tc.wantBody) {
					t.Errorf("wrong body: %s", body)
				}
				status := tc.httpStatus
				if status == 0 {
					status = 200
				}
				return &http.Response{StatusCode: status, Body: io.NopCloser(strings.NewReader(tc.response)), Header: make(http.Header)}, nil
			})}
			err := SendPTZ(client, "protect-eu.ismartlife.me", "camera-1", tc.direction, tc.stop)
			if tc.wantError == "" && err != nil {
				t.Fatalf("unexpected err %v", err)
			}
			if tc.wantError != "" && (err == nil || !strings.Contains(err.Error(), tc.wantError)) {
				t.Fatalf("expected %q, got %v", tc.wantError, err)
			}
		})
	}
}

func TestSendPTZRejectsUnsafeInputs(t *testing.T) {
	client := &http.Client{Transport: ptzRoundTrip(func(*http.Request) (*http.Response, error) { return nil, errors.New("should not send") })}
	cases := []struct{ host, id, dir string }{
		{"evil.example", "abc", "LEFT"},
		{"protect-eu.ismartlife.me", "", "LEFT"},
		{"protect-eu.ismartlife.me", "abc", "SIDEWAYS"},
	}
	for _, c := range cases {
		if err := SendPTZ(client, c.host, c.id, c.dir, false); err == nil {
			t.Errorf("accepted %+v", c)
		}
	}
	if err := SendPTZ(nil, "protect-eu.ismartlife.me", "abc", "LEFT", false); err == nil {
		t.Error("nil client accepted")
	}
}
