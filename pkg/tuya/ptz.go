package tuya

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// SendPTZ uses the Little Elf web API; client must already have a valid web session.
func SendPTZ(client *http.Client, host, deviceID, direction string, stop bool) error {
	if client == nil || strings.TrimSpace(deviceID) == "" {
		return fmt.Errorf("missing client or device ID")
	}
	if host != "protect-eu.ismartlife.me" {
		return fmt.Errorf("untrusted Little Elf host: %q", host)
	}
	path := "/api/jarvis/ptz/start"
	payload := map[string]string{"devId": deviceID}
	if stop {
		path = "/api/jarvis/ptz/end"
	} else {
		switch direction {
		case "UP", "DOWN", "LEFT", "RIGHT", "UP_LEFT", "UP_RIGHT", "DOWN_LEFT", "DOWN_RIGHT":
			payload["direction"] = direction
		default:
			return fmt.Errorf("unsupported direction %q", direction)
		}
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	base := "https://" + host
	req, err := http.NewRequest(http.MethodPost, base+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json; charset=utf-8")
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Origin", base)
	req.Header.Set("Referer", base+"/playback")
	req.Header.Set("X-Requested-With", "XMLHttpRequest")
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("PTZ request: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 8192))
	if err != nil {
		return err
	}
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("PTZ HTTP %d", resp.StatusCode)
	}
	var result struct {
		Success   bool   `json:"success"`
		ErrorCode string `json:"errorCode"`
		ErrorMsg  string `json:"errorMsg"`
	}
	if err := json.Unmarshal(raw, &result); err != nil {
		return fmt.Errorf("invalid PTZ response: %w", err)
	}
	if !result.Success {
		return fmt.Errorf("PTZ denied: %s %s", result.ErrorCode, result.ErrorMsg)
	}
	return nil
}
