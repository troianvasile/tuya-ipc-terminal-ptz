package rtsp

import (
	"time"

	"github.com/pion/rtp"
)

// talkbackRTPClock maintains one continuous RTP clock for the lifetime of a
// camera WebRTC bridge, even when Home Assistant opens a new RTSP session.
type talkbackRTPClock struct {
	started     bool
	sequence    uint16
	timestamp   uint32
	lastAt      time.Time
	lastSamples uint32
}

func (c *talkbackRTPClock) rewrite(input *rtp.Packet, now time.Time) *rtp.Packet {
	if input == nil {
		return nil
	}

	packet := *input
	packet.Header = input.Header
	if !c.started {
		c.sequence = input.SequenceNumber
		c.timestamp = input.Timestamp
		c.started = true
	} else {
		step := c.lastSamples
		if step == 0 {
			step = 160
		}
		if gap := now.Sub(c.lastAt); gap > 250*time.Millisecond {
			elapsedSamples := uint32(gap / time.Millisecond * 8)
			if elapsedSamples > step {
				step = elapsedSamples
			}
		}
		c.sequence++
		c.timestamp += step
	}
	packet.SequenceNumber = c.sequence
	packet.Timestamp = c.timestamp
	c.lastAt = now
	c.lastSamples = uint32(len(input.Payload))
	return &packet
}
