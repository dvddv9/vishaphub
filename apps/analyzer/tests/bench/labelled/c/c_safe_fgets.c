#include <stdio.h>
#include <string.h>

int main(void) {
    char name[64];
    printf("Name: ");
    if (!fgets(name, sizeof name, stdin)) return 1;
    name[strcspn(name, "\n")] = '\0';
    printf("Hello, %s\n", name);
    return 0;
}
