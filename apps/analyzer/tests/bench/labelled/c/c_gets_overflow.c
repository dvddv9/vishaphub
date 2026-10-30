#include <stdio.h>

int main(void) {
    char name[64];
    printf("Name: ");
    gets(name);
    printf("Hello, %s\n", name);
    return 0;
}
