#include <ctype.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) return 1;
    for (const char *p = argv[1]; *p; p++) {
        if (!isdigit((unsigned char)*p) && *p != '.') return 2;
    }
    char *args[] = {"ping", "-c", "1", argv[1], NULL};
    execvp("ping", args);
    return 3;
}
