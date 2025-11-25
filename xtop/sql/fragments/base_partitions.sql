-- Base partitions data source
-- Maps device major/minor numbers to device names from /proc/partitions
SELECT
    LIST_EXTRACT(field_list, 1)::int  AS dev_maj,
    LIST_EXTRACT(field_list, 2)::int  AS dev_min,
    TRIM(LIST_EXTRACT(field_list, 4)) AS devname
FROM (
    SELECT
        REGEXP_EXTRACT_ALL(column0, ' +(\w+)') field_list
    FROM
        read_csv('/proc/partitions', skip=1, header=false)
    WHERE
        field_list IS NOT NULL
)