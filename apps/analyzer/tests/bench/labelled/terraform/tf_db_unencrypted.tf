resource "aws_db_instance" "main" {
  identifier        = "orders"
  engine            = "postgres"
  instance_class    = "db.t3.medium"
  allocated_storage = 50
  storage_encrypted = false
  username          = "app"
  password          = var.db_password
}
