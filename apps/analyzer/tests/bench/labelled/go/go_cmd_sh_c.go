package main

import (
	"net/http"
	"os/exec"
)

func pingHandler(w http.ResponseWriter, r *http.Request) {
	host := r.URL.Query().Get("host")
	out, _ := exec.Command("sh", "-c", "ping -c 1 "+host).CombinedOutput()
	w.Write(out)
}
