package ptz

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPTZHTTPRequiresBearerToken(t *testing.T) {
	h := &ptzHTTPHandler{token: []byte(strings.Repeat("x", 40))}
	for _, auth := range []string{"", "Bearer invalid", "Basic example"} {
		req := httptest.NewRequest(http.MethodPost, "/api/ptz/move", strings.NewReader("{}"))
		req.Header.Set("Authorization", auth)
		resp := httptest.NewRecorder()
		h.ServeHTTP(resp, req)
		if resp.Code != http.StatusUnauthorized {
			t.Fatalf("auth=%q returned %d", auth, resp.Code)
		}
	}
}

func TestPTZHTTPValidatesPathMethodAndPayload(t *testing.T) {
	token := strings.Repeat("s", 40)
	h := &ptzHTTPHandler{token: []byte(token)}
	cases := []struct{ method, path, body string; expected int }{
		{"GET", "/api/ptz/move", "", http.StatusMethodNotAllowed},
		{"POST", "/other", "{}", http.StatusNotFound},
		{"POST", "/api/ptz/move", "{bad", http.StatusBadRequest},
		{"POST", "/api/ptz/move", `{"camera":"Living","direction":"DELETE","duration_ms":400}`, http.StatusBadRequest},
		{"POST", "/api/ptz/move", `{"camera":"Living","direction":"UP","duration_ms":2000}`, http.StatusBadRequest},
		{"POST", "/api/ptz/move", `{"camera":"Living","direction":"UP","unexpected":1}`, http.StatusBadRequest},
	}
	for _, c := range cases {
		req := httptest.NewRequest(c.method, c.path, strings.NewReader(c.body))
		req.Header.Set("Authorization", "Bearer "+token)
		resp := httptest.NewRecorder()
		h.ServeHTTP(resp, req)
		if resp.Code != c.expected {
			t.Fatalf("%s %s %s returned %d expected %d", c.method, c.path, c.body, resp.Code, c.expected)
		}
	}
}

func TestValidPTZDirections(t *testing.T) {
	for _, direction := range []string{"UP", "DOWN", "LEFT", "RIGHT", "UP_LEFT", "UP_RIGHT", "DOWN_LEFT", "DOWN_RIGHT"} {
		if !validPTZDirection(direction) {
			t.Errorf("valid direction rejected %q", direction)
		}
	}
	for _, direction := range []string{"", "stop", "up", "DELETE", "../"} {
		if validPTZDirection(direction) {
			t.Errorf("invalid direction accepted %q", direction)
		}
	}
}
