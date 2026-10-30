package main

import (
	"crypto/md5"
	"encoding/hex"
)

func hashPassword(password string) string {
	sum := md5.Sum([]byte(password))
	return hex.EncodeToString(sum[:])
}
