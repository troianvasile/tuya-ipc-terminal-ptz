package ptz

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/spf13/cobra"
	"tuya-ipc-terminal/pkg/tuya"
)

// ptzHTTPHandler exposes only authenticated, bounded, preset PTZ operations.
// The HTTP listener is an OPTIONAL companion process; the RTSP bridge does
// not listen on this port. Put it behind HTTPS/VPN if HA is on another host.
type ptzHTTPHandler struct {
	token []byte
	locks sync.Map // device ID -> *sync.Mutex; serialize movement per camera
}

func newServeCmd() *cobra.Command {
	var listen, tokenEnv string
	cmd := &cobra.Command{
		Use: "serve",
		Short: "Run optional authenticated PTZ HTTP service for remote Home Assistant",
		RunE: func(_ *cobra.Command, _ []string) error {
			token := os.Getenv(tokenEnv)
			if len(token) < 32 {
				return fmt.Errorf("%s must contain at least 32 characters", tokenEnv)
			}
			if sm == nil {
				return errors.New("storage is not initialized")
			}
			server := &http.Server{
				Addr: listen,
				Handler: &ptzHTTPHandler{token: []byte(token)},
				ReadHeaderTimeout: 5 * time.Second,
				ReadTimeout: 10 * time.Second,
				WriteTimeout: 30 * time.Second,
				IdleTimeout: 30 * time.Second,
			}
			log.Printf("PTZ HTTP listening on %s (authentication required)", listen)
			return server.ListenAndServe()
		},
	}
	cmd.Flags().StringVar(&listen, "listen", "127.0.0.1:8787", "Listen address (localhost by default; use HTTPS/VPN for remote access)")
	cmd.Flags().StringVar(&tokenEnv, "token-env", "LITTLE_ELF_PTZ_TOKEN", "Environment variable containing bearer token (minimum 32 chars)")
	return cmd
}

func (h *ptzHTTPHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	if !strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	given := []byte(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
	if subtle.ConstantTimeCompare(given, h.token) != 1 {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}
	if r.URL.Path != "/api/ptz/move" {
		http.NotFound(w, r)
		return
	}
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var body struct {
		Camera string `json:"camera"`
		Direction string `json:"direction"`
		DurationMS int `json:"duration_ms"`
	}
	r.Body = http.MaxBytesReader(w, r.Body, 2048)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		http.Error(w, "Invalid PTZ JSON", http.StatusBadRequest)
		return
	}
	var extra interface{}
	if decoder.Decode(&extra) != io.EOF {
		http.Error(w, "Unexpected trailing JSON", http.StatusBadRequest)
		return
	}
	if body.DurationMS == 0 {
		body.DurationMS = 400
	}
	if body.DurationMS < 100 || body.DurationMS > 1500 ||
		strings.TrimSpace(body.Camera) == "" ||
		!validPTZDirection(body.Direction) {
		http.Error(w, "Invalid PTZ camera, direction or duration", http.StatusBadRequest)
		return
	}
	client, host, deviceID, err := getClient(body.Camera)
	if err != nil {
		log.Printf("PTZ camera lookup failed: %v", err)
		http.Error(w, "Camera unavailable", http.StatusBadRequest)
		return
	}
	lockAny, _ := h.locks.LoadOrStore(deviceID, &sync.Mutex{})
	mu := lockAny.(*sync.Mutex)
	mu.Lock()
	defer mu.Unlock()

	if err = tuya.SendPTZ(client, host, deviceID, body.Direction, false); err != nil {
		log.Printf("PTZ start failed: %v", err)
		// Attempt stop even when start failed; do not leave movement latched.
		_ = tuya.SendPTZ(client, host, deviceID, "", true)
		http.Error(w, "Camera PTZ rejected request", http.StatusBadGateway)
		return
	}

	timer := time.NewTimer(time.Duration(body.DurationMS) * time.Millisecond)
	select {
	case <-timer.C:
	case <-r.Context().Done():
		timer.Stop()
	}
	if err := tuya.SendPTZ(client, host, deviceID, "", true); err != nil {
		log.Printf("PTZ stop failed for %s: %v", deviceID, err)
		http.Error(w, "PTZ stop failed", http.StatusBadGateway)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte("{\"success\":true}"))
}

func validPTZDirection(dir string) bool {
	switch dir {
	case "UP", "DOWN", "LEFT", "RIGHT", "UP_LEFT", "UP_RIGHT", "DOWN_LEFT", "DOWN_RIGHT":
		return true
	default:
		return false
	}
}
