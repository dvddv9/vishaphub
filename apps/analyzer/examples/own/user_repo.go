package main

import (
    "context"
    "database/sql"
    "time"
)

type UserRepo struct {
    db *sql.DB
}

// BUG 1: unbounded channel — memory leak under load
var events = make(chan string, 0)

// BUG 2: goroutine leak — no context cancellation
func (r *UserRepo) StartWorker() {
    for {
        go func() {
            select {
            case msg := <-events:
                process(msg)
            }
        }()
    }
}

// BUG 3: no timeout, no context
func (r *UserRepo) GetUser(id int) (*sql.Row, error) {
    row := r.db.QueryRow("SELECT * FROM users WHERE id = ?", id)
    return row, nil
}

// BUG 4: retry without backoff, infinite loop
func (r *UserRepo) GetUserWithRetry(id int) (*sql.Row, error) {
    for {
        row, err := r.GetUser(id)
        if err == nil {
            return row, nil
        }
        // no sleep, no max attempts
    }
}

func process(msg string) {
    time.Sleep(time.Second)
}
