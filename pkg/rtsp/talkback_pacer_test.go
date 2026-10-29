package rtsp

import (
	"testing"
	"time"
)

func TestTalkbackPacerUsesEightKilohertzClock(t *testing.T) {
	var pacer talkbackPacer
	pacer.pace(160)
	started := time.Now()
	pacer.pace(160)
	if elapsed := time.Since(started); elapsed < 15*time.Millisecond {
		t.Fatalf("second 20 ms PCMU frame was sent after %s", elapsed)
	}
}
