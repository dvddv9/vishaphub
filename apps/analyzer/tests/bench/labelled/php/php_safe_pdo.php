<?php
$pdo = new PDO("mysql:host=localhost;dbname=shop", "app", getenv("DB_PASSWORD"));
$stmt = $pdo->prepare("SELECT id, name FROM users WHERE id = :id");
$stmt->execute([":id" => (int) $_GET['id']]);
echo json_encode($stmt->fetch(PDO::FETCH_ASSOC));
