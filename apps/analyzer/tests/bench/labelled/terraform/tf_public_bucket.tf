resource "aws_s3_bucket" "exports" {
  bucket = "acme-customer-exports"
  acl    = "public-read"
}
