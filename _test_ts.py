from src.pipeline.verdict import compute_reproducer
print("TS:", compute_reproducer(None, None, 'import express from "express"'))
print("IaC:", compute_reproducer(None, None, 'resource "aws_s3_bucket"'))
print("py:", compute_reproducer(None, None, 'def foo(): pass'))