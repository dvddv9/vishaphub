/* SARD Test Case 234204-v1.0.0
 * CWE-122: Heap-based Buffer Overflow
 * Juliet 1.3 (NSA CAS)
 *
 * Deprecated — alternative: github.com/arichardson/juliet-test-suite-c
 */

typedef struct {
    int intOne;
    int intTwo;
} twoIntsStruct;

void bad() {
    twoIntsStruct * data;
    data = NULL;
    /* FLAW: Using sizeof the pointer and not the data type in malloc() */
    data = (twoIntsStruct *)malloc(sizeof(data));
    data->intOne = 1;
    data->intTwo = 2;
    free(data);
}
