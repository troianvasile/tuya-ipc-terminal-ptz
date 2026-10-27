# Tuya IPC Terminal + PTZ

An independently maintained derivative of Tuya IPC Terminal that adds camera pan/tilt control using the authenticated Little Elf / Tuya IPC web API, while retaining the RTSP bridge and stability improvements.

## Project lineage and attribution

- Original project: [seydx/tuya-ipc-terminal](https://github.com/seydx/tuya-ipc-terminal) — WebRTC-to-RTSP bridge.
- Intermediate fixed fork: [yangyongyongyong/tuya-ipc-terminal-fixed](https://github.com/yangyongyongyong/tuya-ipc-terminal-fixed) — SDP resolution, reconnect/deadlock and client cleanup fixes.
- This derivative: PTZ CLI using the saved web-session cookies and `/api/jarvis/ptz/start` and `/api/jarvis/ptz/end` requests.

The original MIT license and prior authors' notices are retained in `LICENSE` and Git history. This project is not an official Tuya or Little Elf product.

## PTZ commands

After authenticating and discovering cameras as described below:

```bash
./tuya-ipc-terminal ptz move --camera Living --direction LEFT --duration 400ms
./tuya-ipc-terminal ptz move --camera "Baby Room" --direction RIGHT --duration 400ms
./tuya-ipc-terminal ptz stop --camera Living
```

PTZ was physically verified on two Little Elf cameras using the EU web endpoint. Other regions and camera models have not been validated. STOP is attempted after each timed movement but cannot be guaranteed if the network or process fails; keep the camera's travel path clear. The REST helper used in one private Home Assistant deployment is **not included** in this repository.

## Security and limitations

- Never commit `.tuya-data`, saved authentication cookies, user credentials, tokens, or built binaries.
- The web PTZ endpoints are reverse-engineered and may change without notice.
- Test each camera and direction at a short duration before routine use.
- Streaming and PTZ both depend on the vendor web service and working authentication.

---

## Background: fixed fork documentation

# Tuya IPC Terminal (fixed fork)

> **This is a fixed fork** of [seydx/tuya-ipc-terminal](https://github.com/seydx/tuya-ipc-terminal) (MIT).
> Upstream has been inactive for over a year, so fixes live here.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Version](https://img.shields.io/badge/Go-1.21%2B-blue.svg)](https://golang.org/)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()

## Fixes in this fork

| # | Bug | Symptom | Fix |
|---|-----|---------|-----|
| 1 | `generateSDP` hardcoded HD stream info | Requesting `/sd` returned an SDP advertising HEVC while the bridge forwarded H264 → every client failed to decode | SDP now reflects the resolution actually requested (`pkg/rtsp/protocol.go`) |
| 2 | `startStream` held the stream mutex during blocking WebRTC negotiation | First connection worked, **every reconnect hung forever** (deadlock with `RemoveClient`) | Lock released before `bridge.Start()` (`pkg/rtsp/server.go`) |
| 3 | Delayed-shutdown callback ran WebRTC teardown under the stream mutex | Deadlock with track goroutines; stream never shut down, dead WebRTC bridge reused | State flipped under lock, teardown after unlock; fresh bridge created per session |
| 4 | Broken-pipe TCP clients never removed from forwarder | Endless `write: broken pipe` spam, stale sessions | Dead clients deleted on write error (`pkg/rtsp/forwarder.go`) |

Verified against Tuya cameras (H264 SD stream 640x360): 5/5 consecutive snapshot pulls succeed where upstream only ever worked on the first connection.

A powerful CLI tool to connect Tuya Smart Cameras to RTSP clients through reverse-engineered Tuya browser client APIs. Stream your Tuya cameras directly to any RTSP-compatible media player or home automation system.

## ✨ Features

- 🔐 **Dual Authentication**: QR code scanning OR email/password login
- 🌍 **Multi-Region Support**: Support for all Tuya regions (EU, US, China, India)
- 👥 **Multi-User Management**: Handle multiple Tuya Smart accounts simultaneously
- 📡 **Session Persistence**: Automatic session management with validation
- 🎥 **Camera Discovery**: Automatic detection of all cameras from authenticated accounts
- 🎬 **RTSP Server**: WebRTC-to-RTSP bridge for universal compatibility
- 🚀 **Real-time Streaming**: Direct camera access with minimal latency
- 🔄 **Multi-Client Support**: Multiple RTSP clients per camera stream
- 🎯 **H265/HEVC Ready**: Advanced codec support for optimal performance
- 🎤 **Two-Way Audio**: Bidirectional audio for compatible cameras

## 🚀 Quick Start

### Installation

```bash
git clone <repository-url>
cd tuya-ipc-terminal
chmod +x build.sh
./build.sh
```

### 1-Minute Setup

```bash
# 1. Add your Tuya account (interactive)
./tuya-ipc-terminal auth add eu-central user@example.com

# 2. Discover your cameras
./tuya-ipc-terminal cameras refresh

# 3. Start streaming
./tuya-ipc-terminal rtsp start --port 8554

# 4. Watch your cameras
ffplay rtsp://localhost:8554/MyCamera
```

## 📖 Complete Documentation

### 🔐 Authentication Management

#### Two Authentication Methods

**🎯 QR Code**
```bash
./tuya-ipc-terminal auth add eu-central user@example.com
# Scan QR code with Tuya Smart/Smart Life app
```

**🔑 Email/Password**
```bash
./tuya-ipc-terminal auth add eu-central user@example.com --password
# Enter password and select country code interactively
```

#### User Management Commands

```bash
# List all authenticated users
./tuya-ipc-terminal auth list

# Remove user authentication
./tuya-ipc-terminal auth remove eu-central user@example.com

# Refresh expired session
./tuya-ipc-terminal auth refresh eu-central user@example.com

# Test session validity
./tuya-ipc-terminal auth test eu-central user@example.com
```

#### 🌍 Regional Information

```bash
# Show all available regions
./tuya-ipc-terminal auth show-regions

# Show country codes for password authentication
./tuya-ipc-terminal auth show-country-codes
./tuya-ipc-terminal auth show-country-codes --search germany
```

**Available Regions:**
| Region | Endpoint | Description |
|--------|----------|-------------|
| `eu-central` | protect-eu.ismartlife.me | Central Europe |
| `eu-east` | protect-we.ismartlife.me | East Europe |
| `us-west` | protect-us.ismartlife.me | West America |
| `us-east` | protect-ue.ismartlife.me | East America |
| `china` | protect.ismartlife.me | China |
| `india` | protect-in.ismartlife.me | India |

### 📹 Camera Management

```bash
# List all discovered cameras
./tuya-ipc-terminal cameras list

# List cameras for specific user
./tuya-ipc-terminal cameras list --user eu-central_user_at_example_com

# Refresh camera discovery
./tuya-ipc-terminal cameras refresh

# Get detailed camera information
./tuya-ipc-terminal cameras info [camera-id-or-name]
```

### 📡 RTSP Server Management

```bash
# Start RTSP server
./tuya-ipc-terminal rtsp start --port 8554

# Start as background daemon
./tuya-ipc-terminal rtsp start --port 8554 --daemon

# Stop RTSP server
./tuya-ipc-terminal rtsp stop

# Check server status
./tuya-ipc-terminal rtsp status

# List all available camera endpoints
./tuya-ipc-terminal rtsp list-endpoints
```

## 🎬 RTSP Streaming Guide

### 📺 Connecting to Camera Streams

Camera streams are available at:
```
rtsp://localhost:[port]/[camera-name]
rtsp://localhost:[port]/[camera-name]/sd  # Sub-stream (lower quality)
```


### 🏠 Home Automation Integration

**Home Assistant**
```yaml
camera:
  - platform: generic
    stream_source: rtsp://localhost:8554/LivingRoomCamera
    name: "Living Room Camera"
    
  - platform: generic
    stream_source: rtsp://localhost:8554/FrontDoor
    name: "Front Door Camera"
```

**Go2RTC Integration**
```yaml
streams:
  living_room:
    - rtsp://localhost:8554/LivingRoomCamera
  front_door:
    - rtsp://localhost:8554/FrontDoor
```


## 🏗️ Advanced Usage

### 🔧 Running as System Service

**Create systemd service:**
```bash
sudo tee /etc/systemd/system/tuya-rtsp.service > /dev/null <<EOF
[Unit]
Description=Tuya IPC Terminal RTSP Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
ExecStart=$PWD/tuya-ipc-terminal rtsp start --port 8554
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable tuya-rtsp
sudo systemctl start tuya-rtsp
```

### 🔀 Multiple Server Instances

```bash
# Different ports for different purposes
./tuya-ipc-terminal rtsp start --port 8554 --daemon  # Main cameras
./tuya-ipc-terminal rtsp start --port 8555 --daemon  # Backup/secondary
```

### 👥 Multi-User Setup Example

```bash
# Add accounts from different regions
./tuya-ipc-terminal auth add eu-central home@example.com      # European account
./tuya-ipc-terminal auth add --password us-west work@company.com  # US business account
./tuya-ipc-terminal auth add china personal@example.cn        # Chinese account

# Discover all cameras
./tuya-ipc-terminal cameras refresh

# List everything
./tuya-ipc-terminal auth list
./tuya-ipc-terminal cameras list
```

## 🔄 Data Flow

1. **Authentication** → Tuya Cloud API
2. **Discovery** → MQTT + Tuya API
3. **WebRTC Connection** → Direct camera stream
4. **RTP Processing** → Video/audio packet handling
5. **RTSP Server** → Standard protocol output

## 💾 Data Storage

```
.tuya-data/
├── user_eu-central_user_at_example_com.json    # User sessions
├── user_us-west_business_at_company_com.json   # Multiple accounts
└── cameras.json                                # Camera registry
```

## 🛠️ Technical Details

### 🎥 Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| H.264 Video | ✅ | Universal support |
| H.265/HEVC | ✅ | Better compression |
| PCMU Audio | ✅ | Standard quality |
| PCMA Audio | ✅ | Alternative codec |
| HD Streams | ✅ | Main camera stream |
| SD Streams | ✅ | Sub-stream, lower bandwidth |
| Multi-client | ✅ | Multiple viewers per camera |
| Two-way Audio | ✅ | Camera dependent |

### 🎯 Supported Camera Types

| Category | Description | Compatibility |
|----------|-------------|---------------|
| `sp` | Smart cameras | ✅ Full support |
| `dghsxj` | Additional camera type | ✅ Full support |
| Others | Generic Tuya cameras | ⚠️ May work |

## 🐛 Troubleshooting

### 🔐 Authentication Issues

**Problem**: Login fails
```bash
# 1. Check session status
./tuya-ipc-terminal auth test eu-central user@example.com

# 2. Try refreshing
./tuya-ipc-terminal auth refresh eu-central user@example.com

# 3. Re-authenticate if needed
./tuya-ipc-terminal auth remove eu-central user@example.com
./tuya-ipc-terminal auth add eu-central user@example.com
```

**Problem**: Country code not found (password login)
```bash
# Search for your country
./tuya-ipc-terminal auth show-country-codes --search germany
./tuya-ipc-terminal auth show-country-codes --search "united states"
```

### 📹 Camera Discovery Issues

**Problem**: No cameras found
```bash
# 1. Verify authentication
./tuya-ipc-terminal auth list

# 2. Force refresh
./tuya-ipc-terminal cameras refresh

# 3. Check if cameras are online in Tuya Smart app
./tuya-ipc-terminal cameras list --verbose
```

### 📡 RTSP Connection Issues

**Problem**: Can't connect to stream
```bash
# 1. Check server status
./tuya-ipc-terminal rtsp status

# 2. List available streams
./tuya-ipc-terminal rtsp list-endpoints

# 3. Test with simple player
ffplay rtsp://localhost:8554/CameraName
```

**Problem**: Poor stream quality
```bash
# Try sub-stream for lower bandwidth
ffplay rtsp://localhost:8554/CameraName/sd

# Check camera capabilities
./tuya-ipc-terminal cameras info "Camera Name"
```

### Development Setup

```bash
git clone <repository-url>
cd tuya-ipc-terminal
go mod download
go run main.go --help
```

## ⚠️ Limitations & Considerations

### Technical Limitations
- 🌐 Requires active internet connection to Tuya servers
- ☁️ Dependent on Tuya Cloud availability
- 📱 QR authentication requires mobile app
- 🔧 Some advanced camera features may not be supported

### Security Considerations
- 🔒 Sessions stored locally in JSON files
- 🛡️ No additional encryption beyond Tuya's implementation
- 🔥 Firewall configuration recommended for external access
- 🔐 Consider network security for RTSP streams

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

This tool is created through reverse engineering of Tuya's web client APIs. Use responsibly and ensure compliance with:

- Tuya's Terms of Service
- Local privacy laws and regulations
- Camera usage regulations in your jurisdiction

The authors are not responsible for any issues arising from the use of this software.

## 🆘 Support

Having issues? Here's how to get help:

1. 📖 Check this README for common solutions
2. 🐛 Search existing [GitHub Issues](link-to-issues)
3. 💬 Create a new issue with:
   - Your operating system
   - Go version (`go version`)
   - Error messages
   - Steps to reproduce

---

**⭐ If this project helps you, please consider giving it a star on GitHub!**