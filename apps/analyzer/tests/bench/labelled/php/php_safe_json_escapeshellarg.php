<?php
$prefs = json_decode($_COOKIE['prefs'] ?? "{}", true);
echo $prefs['theme'] ?? "light";
$host = escapeshellarg($_GET['host'] ?? "127.0.0.1");
echo shell_exec("ping -c 1 " . $host);
