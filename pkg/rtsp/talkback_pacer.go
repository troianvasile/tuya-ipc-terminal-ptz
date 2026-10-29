package rtsp

import "time"

// talkbackPacer releases PCMU samples at the negotiated 8 kHz playout rate.
// It is called while talkbackController serializes writes, so no extra locking
// is required. This is a transport guard; RTP headers remain untouched.
type talkbackPacer struct {
	next time.Time
}

func (p *talkbackPacer) pace(samples int) {
	if samples <= 0 {
		return
	}
	now := time.Now()
	if p.next.IsZero() || now.Sub(p.next) > 250*time.Millisecond {
		p.next = now
	}
	if wait := time.Until(p.next); wait > 0 {
		time.Sleep(wait)
	}
	p.next = p.next.Add(time.Duration(samples) * time.Second / 8000)
}
