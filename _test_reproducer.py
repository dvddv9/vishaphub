from src.pipeline.verdict import compute_reproducer

print("tf:", compute_reproducer(None, None, 'resource "aws_s3_bucket"'))
print("ts:", compute_reproducer(None, None, 'import express from "express"'))
print("py:", compute_reproducer(None, None, 'def foo(): pass'))