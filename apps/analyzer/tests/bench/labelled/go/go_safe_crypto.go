package main

import (
	"crypto/rand"
	"encoding/hex"
	"os"
	"path/filepath"
)

func resetToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

func readUpload(name string) ([]byte, error) {
	return os.ReadFile(filepath.Join("/srv/uploads", filepath.Base(name)))
}
