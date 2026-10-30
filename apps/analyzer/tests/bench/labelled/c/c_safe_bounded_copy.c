#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    char dest[16];
    if (argc < 2 || strlen(argv[1]) >= sizeof dest) return 1;
    snprintf(dest, sizeof dest, "%s", argv[1]);
    printf("%s\n", dest);
    return 0;
}
