package main

import (
	"math/rand"
	"strconv"
)

func resetToken() string {
	return strconv.FormatInt(rand.Int63(), 36)
}
