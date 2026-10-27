package rtsp

import (
 "errors"
 "fmt"
 "sync"
)

// talkbackController serializes speaker state transitions with incoming audio.
// A failed enable is retried by the next audio packet.
type talkbackController struct {
 mu sync.Mutex
 enabled bool
 closed bool
}

func (t *talkbackController) forward(enable func(int) error, write func() error) error {
 t.mu.Lock()
 defer t.mu.Unlock()
 if t.closed { return errors.New("talkback closed") }
 if !t.enabled {
  if err := enable(1); err != nil { return fmt.Errorf("enable camera speaker: %w", err) }
  t.enabled = true
 }
 if err := write(); err != nil { return fmt.Errorf("forward talkback RTP: %w", err) }
 return nil
}

func (t *talkbackController) close(disable func(int) error) error {
 t.mu.Lock()
 defer t.mu.Unlock()
 t.closed = true
 if !t.enabled { return nil }
 if err := disable(0); err != nil { return fmt.Errorf("disable camera speaker: %w", err) }
 t.enabled = false
 return nil
}
