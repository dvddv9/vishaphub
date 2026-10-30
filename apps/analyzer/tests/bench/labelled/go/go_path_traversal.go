package main

import (
	"net/http"
	"os"
	"path/filepath"
)

func download(w http.ResponseWriter, r *http.Request) {
	data, err := os.ReadFile(filepath.Join("/srv/uploads", r.URL.Query().Get("f")))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	w.Write(data)
}
