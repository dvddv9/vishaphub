package main

import (
	"net"
	"net/http"
	"os/exec"
)

func pingHandler(w http.ResponseWriter, r *http.Request) {
	ip := net.ParseIP(r.URL.Query().Get("host"))
	if ip == nil {
		http.Error(w, "bad host", http.StatusBadRequest)
		return
	}
	out, _ := exec.Command("ping", "-c", "1", ip.String()).CombinedOutput()
	w.Write(out)
}
