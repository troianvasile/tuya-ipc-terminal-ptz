package rtsp

import (
	"time"

	"github.com/pion/rtp"
)

// talkbackRTPClock gives every incoming RTSP talkback session one continuous
// outgoing RTP sequence/timestamp space for the lifetime of a Tuya WebRTC
// bridge. A new microphone press, TTS source, or RTSP connection can otherwise
// reset its RTP counters, which confuses the camera's jitter buffer.
//
// The caller must serialize calls. WebRTCBridge calls rewrite inside
// talkbackController.forward, which holds the controller mutex.
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

	// Shallow-copy the packet and its RTP header. Only sequence and timestamp
	// are rewritten. The source packet must remain untouched.
	packet := *input
	packet.Header = input.Header

	if !c.started {
		// Start with the first source's counters; do not reset on later RTSP
		// connections or on subsequent PTT button presses.
		c.sequence = input.SequenceNumber
		c.timestamp = input.Timestamp
		c.started = true
	} else {
		step := c.lastSamples
		if step == 0 {
			step = 160 // 20ms of PCMU/8000 fallback for malformed/empty input
		}

		// Preserve the elapsed 8-kHz RTP time when audio is stopped between
		// presses. For normal continuous packets use exact sample counts, so
		// scheduler jitter doesn't affect timestamps.
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
	// One PCMU byte encodes one 8-kHz sample.
	c.lastSamples = uint32(len(input.Payload))
	return &packet
}
