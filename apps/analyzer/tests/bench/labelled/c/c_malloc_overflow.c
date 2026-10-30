#include <stdint.h>
#include <stdlib.h>

uint32_t *make_table(uint32_t count) {
    uint32_t *table = malloc(count * sizeof(uint32_t));
    if (!table) return NULL;
    for (uint32_t i = 0; i < count; i++) table[i] = i;
    return table;
}
