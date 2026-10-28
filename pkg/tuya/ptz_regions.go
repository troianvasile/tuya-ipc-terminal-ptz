package tuya

// allowedPTZHosts are the authenticated Little Elf web region hosts recognized
// by this project's auth flow. Never use an arbitrary host from session JSON:
// session files are local mutable data, and PTZ sends cookies to this endpoint.
var allowedPTZHosts = map[string]struct{}{
	"protect-eu.ismartlife.me": {},
	"protect-we.ismartlife.me": {},
	"protect-us.ismartlife.me": {},
	"protect-ue.ismartlife.me": {},
	"protect.ismartlife.me": {},
	"protect-in.ismartlife.me": {},
}

// IsAllowedPTZHost requires the exact lower-case host issued by the known
// region configuration. Ports, schemes, redirects, suffix tricks and arbitrary
// subdomains are intentionally rejected.
func IsAllowedPTZHost(host string) bool {
	_, allowed := allowedPTZHosts[host]
	return allowed
}
