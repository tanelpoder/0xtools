-- Computed columns that are derived from base columns
-- These are always available in the enriched_samples CTE
-- Usage: Include these column definitions in SELECT clause

-- Time bucket columns for time series aggregation
EXTRACT(YEAR FROM TIMESTAMP)::VARCHAR AS YYYY,
LPAD(EXTRACT(MONTH FROM TIMESTAMP)::VARCHAR, 2, '0') AS MM,
LPAD(EXTRACT(DAY FROM TIMESTAMP)::VARCHAR, 2, '0') AS DD,
LPAD(EXTRACT(HOUR FROM TIMESTAMP)::VARCHAR, 2, '0') AS HH,
LPAD(EXTRACT(MINUTE FROM TIMESTAMP)::VARCHAR, 2, '0') AS MI,
LPAD(EXTRACT(SECOND FROM TIMESTAMP)::VARCHAR, 2, '0') AS SS,
-- 10-second bucket (00, 10, 20, 30, 40, 50)
LPAD((FLOOR(EXTRACT(SECOND FROM TIMESTAMP) / 10) * 10)::VARCHAR, 2, '0') AS S10,

-- Filename with numbers replaced by wildcards
COALESCE(REGEXP_REPLACE(FILENAME, '[0-9]+', '*', 'g'), '-') AS FILENAMESUM,

-- File extension extraction
CASE
    WHEN FILENAME IS NULL THEN '-'
    WHEN REGEXP_MATCHES(FILENAME, '\.([^\.]+)$') THEN REGEXP_EXTRACT(FILENAME, '(\.([^\.]+))$', 1)
    ELSE '-'
END AS FEXT,

-- Normalized command name (numbers replaced with *)
CASE 
    WHEN COMM LIKE 'ora_p%' 
    THEN regexp_replace(COMM, '(?:p[0-9a-z]+_)', 'p*_', 'g')
    ELSE regexp_replace(COMM, '[0-9]+', '*', 'g')
END AS COMM2,

-- Connection info from extra_info JSON
CASE 
    WHEN EXTRA_INFO LIKE '%"connection"%' 
    THEN json_extract_string(EXTRA_INFO, '$.connection')
    ELSE '-'
END AS CONNECTION,

-- Connection variants and normalized forms
-- CONNECTION2: remove IPv4-mapped IPv6 prefix ::ffff:
COALESCE(
    REGEXP_REPLACE(
        COALESCE(samples.CONNECTION, json_extract_string(EXTRA_INFO, '$.connection')), 
        '::ffff:', '', 'g'
    ),
    '-'
) AS CONNECTION2,

-- CONNECTIONSUM: wildcard destination port in patterns like "ip1->ip2:PORT"
COALESCE(
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            COALESCE(samples.CONNECTION, json_extract_string(EXTRA_INFO, '$.connection')),
            '::ffff:', '', 'g'
        ),
        '(->.*:)[0-9]+', '\1[*]'
    ),
    '-'
) AS CONNECTIONSUM,

-- CONNECTIONSUM2: wildcard any port suffix occurrences ":PORT" globally
COALESCE(
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            COALESCE(samples.CONNECTION, json_extract_string(EXTRA_INFO, '$.connection')),
            '::ffff:', '', 'g'
        ),
        '(:)[0-9]+', '\1[*]', 'g'
    ),
    '-'
) AS CONNECTIONSUM2
