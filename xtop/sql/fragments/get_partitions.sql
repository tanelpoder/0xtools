-- Block device metadata fragment with JOIN condition
-- Note: This depends on iorqend being present for dev_maj/dev_min columns
LEFT OUTER JOIN (
    SELECT
        LIST_EXTRACT(field_list, 1)::INT  AS dev_maj,
        LIST_EXTRACT(field_list, 2)::INT  AS dev_min,
        TRIM(LIST_EXTRACT(field_list, 4)) AS devname
    FROM (
        SELECT
            REGEXP_EXTRACT_ALL(column0, ' +(\w+)') field_list
        FROM
            read_csv('/proc/partitions', skip=1, header=false)
        WHERE
            field_list IS NOT NULL
    )
) part ON io.dev_maj = part.dev_maj AND io.dev_min = part.dev_min