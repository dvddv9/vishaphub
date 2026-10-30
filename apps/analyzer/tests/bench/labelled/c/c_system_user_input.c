#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    char cmd[256];
    if (argc < 2) return 1;
    snprintf(cmd, sizeof cmd, "ping -c 1 %s", argv[1]);
    return system(cmd);
}
