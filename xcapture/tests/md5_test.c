#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "md5.h"

#define MAX_LINE_LENGTH 10000

/* Helper function to remove newline characters */
void strip_newline(char *str) {
    size_t len = strlen(str);
    if (len > 0 && str[len-1] == '\n') {
        str[len-1] = '\0';
    }
}

/* Helper function to convert raw MD5 digest to hex string */
void md5_to_hex(const unsigned char digest[16], char *hex_output) {
    for (int i = 0; i < 16; i++) {
        sprintf(&hex_output[i*2], "%02x", digest[i]);
    }
    hex_output[32] = '\0';
}

int main(int argc, char *argv[]) {
    FILE *input_file;
    char line[MAX_LINE_LENGTH];
    unsigned char digest[16]; /* Raw MD5 digest (16 bytes) */
    char md5_hex[33]; /* MD5 hash as hex string (32 chars + null terminator) */
    MD5_CTX context;

    /* Check arguments */
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <input_file>\n", argv[0]);
        return 1;
    }

    /* Open the input file */
    input_file = fopen(argv[1], "r");
    if (!input_file) {
        perror("Error opening input file");
        return 1;
    }

    /* Process each line */
    while (fgets(line, MAX_LINE_LENGTH, input_file)) {
        strip_newline(line);

        /* Calculate MD5 hash */
        MD5_Init(&context);
        MD5_Update(&context, (const unsigned char *)line, strlen(line));
        MD5_Final(digest, &context);

        /* Convert binary digest to hex string */
        md5_to_hex(digest, md5_hex);

        /* Output hash and original string */
        printf("%s %s\n", md5_hex, line);
    }

    fclose(input_file);
    return 0;
}
