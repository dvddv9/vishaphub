/* C command injection demo (source -> sink).
 * Source: argv[1] (command-line argument)
 * Sink: system() (shell command execution)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    char buf[256];

    if (argc > 1) {
        strcpy(buf, argv[1]);
        system(buf);
    }

    return 0;
}
