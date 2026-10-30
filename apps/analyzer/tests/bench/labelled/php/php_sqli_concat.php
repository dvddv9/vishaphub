<?php
$conn = new mysqli("localhost", "app", getenv("DB_PASSWORD"), "shop");
$result = mysqli_query($conn, "SELECT * FROM users WHERE id = " . $_GET['id']);
while ($row = mysqli_fetch_assoc($result)) {
    echo json_encode($row);
}
