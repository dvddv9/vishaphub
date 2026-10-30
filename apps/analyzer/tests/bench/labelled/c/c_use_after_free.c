#include <stdlib.h>
#include <string.h>

void handle(const char *input) {
    char *buf = malloc(64);
    if (!buf) return;
    strncpy(buf, input, 63);
    buf[63] = '\0';
    free(buf);
    buf[0] = 'X';
}
