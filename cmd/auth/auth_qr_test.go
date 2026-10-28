package auth

import "testing"

func TestConfirmQRLoginEmailRejectsDifferentAccountForWebManager(t *testing.T) {
	t.Setenv("TUYA_QR_WEB", "1")
	if err := confirmQRLoginEmail("expected@example.com", "other@example.com"); err == nil {
		t.Fatal("web QR login accepted a different Tuya account")
	}
}

func TestConfirmQRLoginEmailAcceptsExpectedAccountForWebManager(t *testing.T) {
	t.Setenv("TUYA_QR_WEB", "1")
	if err := confirmQRLoginEmail("expected@example.com", "expected@example.com"); err != nil {
		t.Fatalf("web QR login rejected expected account: %v", err)
	}
}
