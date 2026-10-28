package ptz

import (
	"errors"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"time"

	"tuya-ipc-terminal/pkg/storage"
	"tuya-ipc-terminal/pkg/tuya"

	"github.com/spf13/cobra"
	"golang.org/x/net/publicsuffix"
)

var sm *storage.StorageManager

func SetStorageManager(s *storage.StorageManager) { sm = s }

func NewPTZCmd() *cobra.Command {
	cmd := &cobra.Command{Use: "ptz", Short: "Control Little Elf camera pan/tilt using saved session"}
	var device string
	var duration time.Duration
	var direction string
	move := &cobra.Command{Use: "move", Short: "Move camera for a bounded duration and stop", RunE: func(cmd *cobra.Command, args []string) error {
		if duration < 100*time.Millisecond || duration > 1500*time.Millisecond {
			return errors.New("duration must be between 100ms and 1500ms")
		}
		direction = strings.ToUpper(strings.ReplaceAll(strings.TrimSpace(direction), "-", "_"))
		client, host, id, err := getClient(device)
		if err != nil {
			return err
		}
		// Always attempt STOP even if START fails. Cloud failure can still prevent STOP.
		defer func() {
			if e := tuya.SendPTZ(client, host, id, "", true); e != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "WARNING: PTZ stop failed: %v\n", e)
			}
		}()
		if err := tuya.SendPTZ(client, host, id, direction, false); err != nil {
			return err
		}
		time.Sleep(duration)
		return nil
	}}
	move.Flags().StringVar(&device, "camera", "", "Camera name or device ID (required)")
	move.Flags().StringVar(&direction, "direction", "", "UP, DOWN, LEFT, RIGHT (or diagonal)")
	move.Flags().DurationVar(&duration, "duration", 400*time.Millisecond, "Movement duration (100ms to 1500ms)")
	_ = move.MarkFlagRequired("camera")
	_ = move.MarkFlagRequired("direction")
	cmd.AddCommand(move)
	var stopDevice string
	stop := &cobra.Command{Use: "stop", Short: "Stop moving a camera", RunE: func(cmd *cobra.Command, args []string) error {
		client, host, id, err := getClient(stopDevice)
		if err != nil {
			return err
		}
		return tuya.SendPTZ(client, host, id, "", true)
	}}
	stop.Flags().StringVar(&stopDevice, "camera", "", "Camera name or device ID (required)")
	_ = stop.MarkFlagRequired("camera")
	cmd.AddCommand(stop)
	return cmd
}

func getClient(name string) (*http.Client, string, string, error) {
	if sm == nil {
		return nil, "", "", errors.New("storage not configured")
	}
	cameras, err := sm.GetAllCameras()
	if err != nil {
		return nil, "", "", err
	}
	var selected *storage.CameraInfo
	for i := range cameras {
		c := &cameras[i]
		if strings.EqualFold(c.DeviceName, name) || strings.EqualFold(c.DeviceID, name) {
			if selected != nil {
				return nil, "", "", fmt.Errorf("ambiguous camera %q; use device ID", name)
			}
			selected = c
		}
	}
	if selected == nil {
		return nil, "", "", fmt.Errorf("unknown camera %q; check 'cameras list'", name)
	}
	users, err := sm.ListUsers()
	if err != nil {
		return nil, "", "", err
	}
	for _, u := range users {
		if u.UserKey != selected.UserKey || u.SessionData == nil {
			continue
		}
		session := u.SessionData
		if !tuya.IsAllowedPTZHost(session.ServerHost) {
			return nil, "", "", fmt.Errorf("unexpected server host %q", session.ServerHost)
		}
		jar, err := cookiejar.New(&cookiejar.Options{PublicSuffixList: publicsuffix.List})
		if err != nil {
			return nil, "", "", err
		}
		var cookies []*http.Cookie
		for _, c := range session.Cookies {
			if c == nil {
				continue
			}
			cookies = append(cookies, &http.Cookie{Name: c.Name, Value: c.Value, Path: c.Path, Secure: c.Secure, HttpOnly: c.HttpOnly, Expires: c.Expires})
		}
		if len(cookies) == 0 {
			return nil, "", "", errors.New("saved session contains no cookies")
		}
		jar.SetCookies(&url.URL{Scheme: "https", Host: session.ServerHost}, cookies)
		client := &http.Client{Jar: jar, Timeout: 12 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
		return client, session.ServerHost, selected.DeviceID, nil
	}
	return nil, "", "", fmt.Errorf("no saved account session for camera %q", name)
}
