package rtsp

import (
	"errors"
	"fmt"
	"sync"
	"time"

	"tuya-ipc-terminal/pkg/core"
)

// Stop the physical camera speaker shortly after the last RTP packet. This
// allows the next PTT press (even on a reused RTSP/WebRTC connection) to send
// a fresh SendSpeaker(1), rather than relying on one enable per camera session.
const defaultTalkbackIdleTimeout = 900 * time.Millisecond

// talkbackController serializes speaker state transitions and RTP writes.
// The camera's WebRTC connection remains active when the speaker is disabled.
type talkbackController struct {
	mu           sync.Mutex
	enabled      bool
	closed       bool
	idleTimer    *time.Timer
	idleTimeout  time.Duration // override in tests; zero uses default
	lastPacketAt time.Time
}

func (t *talkbackController) forward(speaker func(int) error, write func() error) error {
	t.mu.Lock()
	defer t.mu.Unlock()

	if t.closed {
		return errors.New("talkback closed")
	}

	if !t.enabled {
		if err := speaker(1); err != nil {
			return fmt.Errorf("enable camera speaker: %w", err)
		}
		t.enabled = true
		core.Logger.Debug().Msg("Talkback: speaker enabled")
	}

	if err := write(); err != nil {
		return fmt.Errorf("forward talkback RTP: %w", err)
	}

	t.lastPacketAt = time.Now()
	t.scheduleIdleLocked(speaker)
	return nil
}

func (t *talkbackController) timeout() time.Duration {
	if t.idleTimeout > 0 {
		return t.idleTimeout
	}
	return defaultTalkbackIdleTimeout
}

// Called while mu is locked. Resetting the existing timer avoids creating a
// new timer/goroutine for every incoming audio packet.
func (t *talkbackController) scheduleIdleLocked(speaker func(int) error) {
	if t.idleTimer == nil {
		t.idleTimer = time.AfterFunc(t.timeout(), func() {
			t.disableAfterIdle(speaker)
		})
	} else {
		t.idleTimer.Reset(t.timeout())
	}
}

func (t *talkbackController) disableAfterIdle(speaker func(int) error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	if t.closed || !t.enabled {
		return
	}

	// A timer callback already queued before Reset must not turn off the
	// speaker while fresh packets are still arriving.
	if remaining := t.timeout() - time.Since(t.lastPacketAt); remaining > 0 {
		t.idleTimer.Reset(remaining)
		return
	}

	if err := t.disableLocked(speaker); err != nil {
		core.Logger.Warn().Err(err).Msg("Talkback: failed to disable camera speaker after idle")
	}
}

// disableLocked resets the local state even when the MQTT command fails.
// The next audio packet will retry SendSpeaker(1) instead of staying latched.
func (t *talkbackController) disableLocked(speaker func(int) error) error {
	if !t.enabled {
		return nil
	}
	t.enabled = false
	if err := speaker(0); err != nil {
		return fmt.Errorf("disable camera speaker: %w", err)
	}
	core.Logger.Debug().Msg("Talkback: speaker disabled")
	return nil
}

func (t *talkbackController) close(speaker func(int) error) error {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.closed = true
	if t.idleTimer != nil {
		t.idleTimer.Stop()
		t.idleTimer = nil
	}
	return t.disableLocked(speaker)
}
