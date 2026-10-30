<?php
$pages = ["home" => "home.php", "about" => "about.php"];
$page = $_GET['page'] ?? "home";
if (!isset($pages[$page])) {
    http_response_code(404);
    exit;
}
echo "<h1>Hello, " . htmlspecialchars($_GET['name'] ?? "", ENT_QUOTES, "UTF-8") . "</h1>";
include($pages[$page]);
