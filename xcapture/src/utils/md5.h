#ifndef __MD5_H
#define __MD5_H

#include <stdint.h>
#include <string.h>

// MD5 context structure
typedef struct {
    uint32_t state[4];      // State (ABCD)
    uint32_t count[2];      // Number of bits, mod 2^64 (LSB first)
    unsigned char buffer[64]; // Input buffer
} MD5_CTX;

// MD5 functions - public interface
void MD5_Init(MD5_CTX *context);
void MD5_Update(MD5_CTX *context, const unsigned char *input, unsigned int inputLen);
void MD5_Final(unsigned char digest[16], MD5_CTX *context);

// Stack hash function - use standard C uint64_t
uint64_t hash_stack(uint64_t *stack, int stack_len);

#endif /* __MD5_H */
