package ptz

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func TestRunBoundedMove(t *testing.T) {
	cases := []struct {
		name      string
		startErr  error
		stopErr   error
		wantError string
	}{
		{name: "success"},
		{name: "start failure still stops", startErr: errors.New("start rejected"), wantError: "start rejected"},
		{name: "stop failure makes command fail", stopErr: errors.New("stop rejected"), wantError: "stop rejected"},
		{name: "both failures reported", startErr: errors.New("start rejected"), stopErr: errors.New("stop rejected"), wantError: "stop rejected"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var calls []bool
			slept := false
			err := runBoundedMove(func(stop bool) error {
				calls = append(calls, stop)
				if stop {
					return tc.stopErr
				}
				return tc.startErr
			}, 400*time.Millisecond, func(d time.Duration) {
				if d != 400*time.Millisecond {
					t.Fatalf("unexpected duration: %s", d)
				}
				slept = true
			})
			if len(calls) != 2 || calls[0] || !calls[1] {
				t.Fatalf("unexpected order: %v", calls)
			}
			if slept != (tc.startErr == nil) {
				t.Fatalf("sleep mismatch: %v", slept)
			}
			if tc.wantError == "" && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if tc.wantError != "" && (err == nil || !strings.Contains(err.Error(), tc.wantError)) {
				t.Fatalf("expected error containing %q; got %v", tc.wantError, err)
			}
			if tc.startErr != nil && tc.stopErr != nil && !strings.Contains(err.Error(), tc.startErr.Error()) {
				t.Fatalf("start error lost: %v", err)
			}
		})
	}
}
