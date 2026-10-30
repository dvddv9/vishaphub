variable "db_password" {
  type      = string
  sensitive = true
}

resource "aws_db_instance" "main" {
  identifier        = "orders"
  engine            = "postgres"
  instance_class    = "db.t3.medium"
  allocated_storage = 50
  storage_encrypted = true
  kms_key_id        = aws_kms_key.db.arn
  username          = "app"
  password          = var.db_password
}
