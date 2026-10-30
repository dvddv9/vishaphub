#include <string.h>

int main(int argc, char **argv) {
    char dest[16];
    if (argc < 2) return 1;
    strcpy(dest, argv[1]);
    return dest[0] == 'a';
}
