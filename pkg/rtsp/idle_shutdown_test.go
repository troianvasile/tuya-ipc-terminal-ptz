package rtsp

import (
	"testing"
	"time"

	"tuya-ipc-terminal/pkg/storage"
)

func TestIdleShutdownClosesWebRTCBridgeAndRemovesStream(t *testing.T) {
	cam := &storage.CameraInfo{DeviceName: "Baby room"}
	server := &RTSPServer{streams: map[string]*CameraStream{}}
	bridge := NewWebRTCBridge(cam, "sd", nil, nil)
	stream := &CameraStream{
		camera: cam,
		clients: make(map[string]*RTSPClient),
		active: true,
		webrtcBridge: bridge,
		shutdownDelay: 10 * time.Millisecond,
		server: server,
		streamId: "baby-sd",
	}
	server.streams[stream.streamId] = stream

	stream.mutex.Lock()
	stream.scheduleShutdown()
	stream.mutex.Unlock()

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		server.mutex.RLock()
		_, exists := server.streams[stream.streamId]
		server.mutex.RUnlock()

		bridge.mutex.RLock()
		stopped := bridge.stopped
		bridge.mutex.RUnlock()

		if !exists && stopped {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("idle stream was not removed and its WebRTC bridge stopped")
}

func TestIdleShutdownCanceledWhenClientRejoins(t *testing.T) {
	cam := &storage.CameraInfo{DeviceName: "Living"}
	server := &RTSPServer{streams: map[string]*CameraStream{}}
	stream := &CameraStream{
		camera: cam,
		clients: make(map[string]*RTSPClient),
		active: true,
		shutdownDelay: 20 * time.Millisecond,
		server: server,
		streamId: "living-sd",
	}
	server.streams[stream.streamId] = stream

	stream.mutex.Lock()
	stream.scheduleShutdown()
	stream.mutex.Unlock()
	stream.AddClient(&RTSPClient{session:"test-client"})

	time.Sleep(100*time.Millisecond)
	server.mutex.RLock()
	actual := server.streams[stream.streamId]
	server.mutex.RUnlock()
	if actual != stream {
		t.Fatal("active client did not cancel pending shutdown")
	}
	stream.mutex.RLock()
	active := stream.active
	stream.mutex.RUnlock()
	if !active {
		t.Fatal("stream became inactive despite a connected client")
	}
}

func TestRemovalCannotDeleteReplacementStream(t *testing.T) {
	server := &RTSPServer{streams: map[string]*CameraStream{}}
	old := &CameraStream{}
	newStream := &CameraStream{}
	server.streams["baby-sd"] = newStream
	server.removeStreamIfCurrent("baby-sd", old)
	if server.streams["baby-sd"] != newStream {
		t.Fatal("stale bridge removed a replacement stream")
	}
	server.removeStreamIfCurrent("baby-sd", newStream)
	if _, exists := server.streams["baby-sd"]; exists {
		t.Fatal("current stream was not removed")
	}
}
