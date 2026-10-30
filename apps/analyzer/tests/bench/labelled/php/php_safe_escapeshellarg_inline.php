<?php
$host = filter_var($_GET['host'] ?? "", FILTER_VALIDATE_IP);
if ($host === false) {
    http_response_code(400);
    exit;
}
echo shell_exec("ping -c 1 " . escapeshellarg($host));
