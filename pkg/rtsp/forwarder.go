package rtsp

import (
	"fmt"
	"net"
	"strconv"
	"strings"
	"sync"
	"time"
	"tuya-ipc-terminal/pkg/core"
	"tuya-ipc-terminal/pkg/utils"

	"github.com/pion/rtp"
)

// RTP transport mode (UDP or TCP)
type TransportMode int

const (
	TransportUDP TransportMode = iota
	TransportTCP               // Interleaved
)

type RTPForwarder struct {
	clients map[string]*RTPClient
	mutex   sync.RWMutex

	// RTP session info
	videoSSRC uint32
	audioSSRC uint32

	// Packet count
	firstVideoPacket bool
	firstAudioPacket bool

	OnBackchannelAudio func(*rtp.Packet)
}

type RTPClient struct {
	sessionID     string
	transportMode TransportMode

	// UDP transport - Outgoing connections (server -> client)
	videoConn *net.UDPConn // For sending video to client
	audioConn *net.UDPConn // For sending audio to client

	// UDP transport - Client addresses
	videoAddr *net.UDPAddr
	audioAddr *net.UDPAddr

	// UDP transport - Client ports
	videoRTPPort          int // Client's video receiving port
	audioRTPPort          int // Client's audio receiving port
	backchannelClientPort int // Client's backchannel sending port

	// UDP backchannel listeners (server side)
	backchannelListener     *net.UDPConn // Server's RTP listener for backchannel
	backchannelRTCPListener *net.UDPConn // Server's RTCP listener for backchannel
	backchannelServerPort   int          // Server's RTP listening port
	backchannelRTCPPort     int          // Server's RTCP listening port

	// TCP interleaved transport
	tcpConn             net.Conn
	videoRTPChannel     byte
	audioRTPChannel     byte
	backAudioRTPChannel byte

	lastActivity time.Time
}

func NewRTPForwarder() *RTPForwarder {
	return &RTPForwarder{
		clients:          make(map[string]*RTPClient),
		videoSSRC:        0, // Default SSRC for video
		audioSSRC:        1, // Default SSRC for audio
		firstVideoPacket: true,
		firstAudioPacket: true,
	}
}

func udpAddress(host string, port int) (*net.UDPAddr, error) {
	if host == "" || port < 1 || port > 65535 {
		return nil, fmt.Errorf("invalid UDP client address")
	}

	return net.ResolveUDPAddr("udp", net.JoinHostPort(host, strconv.Itoa(port)))
}

func updateUDPConnection(conn **net.UDPConn, currentAddr **net.UDPAddr, host string, port int) error {
	if port == 0 {
		if *conn != nil {
			(*conn).Close()
		}
		*conn = nil
		*currentAddr = nil
		return nil
	}

	address, err := udpAddress(host, port)
	if err != nil {
		return err
	}
	if *conn != nil && *currentAddr != nil && (*currentAddr).String() == address.String() {
		return nil
	}

	newConn, err := net.DialUDP("udp", nil, address)
	if err != nil {
		return err
	}
	if *conn != nil {
		(*conn).Close()
	}
	*conn = newConn
	*currentAddr = address
	return nil
}

func (rf *RTPForwarder) AddUDPClient(sessionID, clientHost string, videoRTPPort, audioRTPPort int) error {
	rf.mutex.Lock()
	defer rf.mutex.Unlock()

	// Check if client already exists
	if client, exists := rf.clients[sessionID]; exists {
		// Update existing client with new ports
		client.videoRTPPort = videoRTPPort
		client.audioRTPPort = audioRTPPort
		client.lastActivity = time.Now()

		if err := updateUDPConnection(&client.videoConn, &client.videoAddr, clientHost, videoRTPPort); err != nil {
			return fmt.Errorf("failed to update video UDP connection: %w", err)
		}
		if err := updateUDPConnection(&client.audioConn, &client.audioAddr, clientHost, audioRTPPort); err != nil {
			return fmt.Errorf("failed to update audio UDP connection: %w", err)
		}

		return nil
	}

	client := &RTPClient{
		sessionID:     sessionID,
		transportMode: TransportUDP,
		videoRTPPort:  videoRTPPort,
		audioRTPPort:  audioRTPPort,
		lastActivity:  time.Now(),
	}

	if err := updateUDPConnection(&client.videoConn, &client.videoAddr, clientHost, videoRTPPort); err != nil {
		return fmt.Errorf("failed to create video UDP connection: %w", err)
	}
	if err := updateUDPConnection(&client.audioConn, &client.audioAddr, clientHost, audioRTPPort); err != nil {
		if client.videoConn != nil {
			client.videoConn.Close()
		}
		return fmt.Errorf("failed to create audio UDP connection: %w", err)
	}

	rf.clients[sessionID] = client

	core.Logger.Trace().Msgf("Added UDP RTP client %s (video port:%d, audio port:%d)",
		sessionID, videoRTPPort, audioRTPPort)
	return nil
}

func (rf *RTPForwarder) SetupUDPBackchannel(sessionID string, clientPort int) (int, error) {
	rf.mutex.Lock()
	defer rf.mutex.Unlock()

	client, exists := rf.clients[sessionID]
	if !exists {
		return 0, fmt.Errorf("client %s not found", sessionID)
	}

	if client.transportMode != TransportUDP {
		return 0, fmt.Errorf("client %s is not using UDP transport", sessionID)
	}

	// Store client's backchannel port
	client.backchannelClientPort = clientPort

	// If listeners already exist, return existing port
	if client.backchannelListener != nil {
		return client.backchannelServerPort, nil
	}

	// Allocate consecutive ports for RTP/RTCP
	portPair, err := utils.DefaultPortAllocator.GetConsecutiveUDPPorts(nil, 10)
	if err != nil {
		return 0, fmt.Errorf("failed to allocate UDP ports for backchannel: %v", err)
	}

	// Store listeners and ports
	client.backchannelListener = portPair.RTPListener
	client.backchannelRTCPListener = portPair.RTCPListener
	client.backchannelServerPort = portPair.RTPPort
	client.backchannelRTCPPort = portPair.RTCPPort

	// Start goroutines to handle incoming packets
	go rf.handleUDPBackchannelRTP(sessionID, client.backchannelListener)
	go rf.handleUDPBackchannelRTCP(client.backchannelRTCPListener)

	core.Logger.Trace().Msgf("Setup UDP backchannel for client %s (client ports:%d-%d, server ports:%d-%d)",
		sessionID, clientPort, clientPort+1, portPair.RTPPort, portPair.RTCPPort)

	return portPair.RTPPort, nil
}

func (rf *RTPForwarder) AddTCPClient(sessionID string, conn net.Conn, videoRTPChannel, audioRTPChannel, backAudioRTPChannel byte) error {
	rf.mutex.Lock()
	defer rf.mutex.Unlock()

	// Check if client already exists, update it
	if existingClient, exists := rf.clients[sessionID]; exists {
		core.Logger.Trace().Msgf("TCP client %s already exists, updating channels (video:%d->%d, audio:%d->%d, back:%d->%d)",
			sessionID, existingClient.videoRTPChannel, videoRTPChannel, existingClient.audioRTPChannel, audioRTPChannel, existingClient.backAudioRTPChannel, backAudioRTPChannel)
		existingClient.videoRTPChannel = videoRTPChannel
		existingClient.audioRTPChannel = audioRTPChannel
		existingClient.backAudioRTPChannel = backAudioRTPChannel
		existingClient.lastActivity = time.Now()
		return nil
	}

	client := &RTPClient{
		sessionID:           sessionID,
		transportMode:       TransportTCP,
		tcpConn:             conn,
		videoRTPChannel:     videoRTPChannel,
		audioRTPChannel:     audioRTPChannel,
		backAudioRTPChannel: backAudioRTPChannel,
		lastActivity:        time.Now(),
	}

	rf.clients[sessionID] = client

	core.Logger.Trace().Msgf("Added TCP RTP client %s (video channel:%d, audio channel:%d, back audio channel:%d)",
		sessionID, videoRTPChannel, audioRTPChannel, backAudioRTPChannel)
	return nil
}

func (rf *RTPForwarder) RemoveClient(sessionID string) {
	rf.mutex.Lock()
	defer rf.mutex.Unlock()

	if client, exists := rf.clients[sessionID]; exists {
		if client.transportMode == TransportUDP {
			if client.videoConn != nil {
				client.videoConn.Close()
			}
			if client.audioConn != nil {
				client.audioConn.Close()
			}
			if client.backchannelListener != nil {
				client.backchannelListener.Close()
			}
			if client.backchannelRTCPListener != nil {
				client.backchannelRTCPListener.Close()
			}
		}

		delete(rf.clients, sessionID)
		core.Logger.Trace().Msgf("Removed RTP client %s", sessionID)
	}
}

func (rf *RTPForwarder) ForwardVideoPacket(packet *rtp.Packet) {
	rf.mutex.RLock()
	defer rf.mutex.RUnlock()

	if len(rf.clients) == 0 {
		return
	}

	// Serialize packet
	data, err := packet.Marshal()
	if err != nil {
		core.Logger.Error().Err(err).Msg("Error marshaling video RTP packet")
		return
	}

	// Forward to all clients; drop dead clients on write error
	for sessionID, client := range rf.clients {
		client.lastActivity = time.Now()

		if client.transportMode == TransportUDP {
			if client.videoConn != nil {
				if _, err := client.videoConn.Write(data); err != nil {
					core.Logger.Error().Err(err).Msgf("Error forwarding video packet to UDP client %s", sessionID)
					delete(rf.clients, sessionID)
				}
			}
		} else if client.transportMode == TransportTCP {
			if client.tcpConn != nil {
				if err := rf.sendInterleavedRTP(client.tcpConn, client.videoRTPChannel, data); err != nil {
					core.Logger.Error().Err(err).Msgf("Error forwarding video packet to TCP client %s", sessionID)
					delete(rf.clients, sessionID)
				}
			}
		}
	}
}

func (rf *RTPForwarder) ForwardAudioPacket(packet *rtp.Packet) {
	rf.mutex.RLock()
	defer rf.mutex.RUnlock()

	if len(rf.clients) == 0 {
		return
	}

	// Serialize packet
	data, err := packet.Marshal()
	if err != nil {
		core.Logger.Error().Err(err).Msg("Error marshaling audio RTP packet")
		return
	}

	// Forward to all clients; drop dead clients on write error
	for sessionID, client := range rf.clients {
		client.lastActivity = time.Now()

		if client.transportMode == TransportUDP {
			if client.audioConn != nil {
				if _, err := client.audioConn.Write(data); err != nil {
					core.Logger.Error().Err(err).Msgf("Error forwarding audio packet to UDP client %s", sessionID)
					delete(rf.clients, sessionID)
				}
			}
		} else if client.transportMode == TransportTCP {
			if client.tcpConn != nil {
				if err := rf.sendInterleavedRTP(client.tcpConn, client.audioRTPChannel, data); err != nil {
					core.Logger.Error().Err(err).Msgf("Error forwarding audio packet to TCP client %s", sessionID)
					delete(rf.clients, sessionID)
				}
			}
		}
	}
}

func (rf *RTPForwarder) Stop() {
	// Reset SSRCs
	rf.videoSSRC = 0
	rf.audioSSRC = 1

	// Reset first packet flags
	rf.firstVideoPacket = true
	rf.firstAudioPacket = true

	// Clear all clients
	for sessionID := range rf.clients {
		rf.RemoveClient(sessionID)
	}

	core.Logger.Trace().Msg("RTPForwarder stopped and all clients cleared")
}

func (rf *RTPForwarder) GetClientCount() int {
	rf.mutex.RLock()
	defer rf.mutex.RUnlock()
	return len(rf.clients)
}

func (rf *RTPForwarder) CleanupInactiveClients(timeout time.Duration) {
	rf.mutex.Lock()
	defer rf.mutex.Unlock()

	now := time.Now()
	var toRemove []string

	for sessionID, client := range rf.clients {
		if now.Sub(client.lastActivity) > timeout {
			toRemove = append(toRemove, sessionID)
		}
	}

	for _, sessionID := range toRemove {
		if client, exists := rf.clients[sessionID]; exists {
			if client.transportMode == TransportUDP {
				if client.videoConn != nil {
					client.videoConn.Close()
				}
				if client.audioConn != nil {
					client.audioConn.Close()
				}
				if client.backchannelListener != nil {
					client.backchannelListener.Close()
				}
				if client.backchannelRTCPListener != nil {
					client.backchannelRTCPListener.Close()
				}
			}
			delete(rf.clients, sessionID)
			core.Logger.Trace().Msgf("Cleaned up inactive RTP client %s", sessionID)
		}
	}
}

func (rf *RTPForwarder) handleUDPBackchannelRTP(sessionID string, listener *net.UDPConn) {
	defer listener.Close()

	buffer := make([]byte, 1500)

	for {
		n, _, err := listener.ReadFromUDP(buffer)
		if err != nil {
			if !strings.Contains(err.Error(), "closed") {
				core.Logger.Error().Err(err).Msgf("Error reading UDP RTP backchannel for client %s", sessionID)
			}
			break
		}

		// Parse RTP packet
		packet := &rtp.Packet{}
		if err := packet.Unmarshal(buffer[:n]); err != nil {
			continue
		}

		// Forward to WebRTC bridge
		if rf.OnBackchannelAudio != nil {
			rf.OnBackchannelAudio(packet)
		}
	}
}

func (rf *RTPForwarder) handleUDPBackchannelRTCP(listener *net.UDPConn) {
	defer listener.Close()

	buffer := make([]byte, 1500)

	for {
		_, _, err := listener.ReadFromUDP(buffer)
		if err != nil {
			// Ignore
			break
		}

		// Simply discard RTCP packets
	}
}

func (rf *RTPForwarder) sendInterleavedRTP(conn net.Conn, channel byte, rtpData []byte) error {
	// Interleaved format: $ + channel + length(2 bytes) + RTP data
	header := make([]byte, 4)
	header[0] = '$'                     // Magic byte
	header[1] = channel                 // Channel number
	header[2] = byte(len(rtpData) >> 8) // Length high byte
	header[3] = byte(len(rtpData))      // Length low byte

	// Send header + data in one write to avoid fragmentation
	fullPacket := append(header, rtpData...)

	if _, err := conn.Write(fullPacket); err != nil {
		return err
	}

	return nil
}
