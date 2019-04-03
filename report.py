#  report.py -- Linux Process Snapper by Tanel Poder
#  Copyright 2019 Tanel Poder
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

# query/report code

from itertools import groupby

import proc
import logging

def flatten(li):
    return [item for sublist in li for item in sublist]


### ASCII table output ###
def output_table_report(report, dataset):
    max_field_width = 60
    header_fmts, field_fmts = [], []
    total_field_width = 0

    if dataset:
        col_idx = 0
        for source, cols, expr, token in report.full_projection():
            if token in ('pid', 'task', 'samples'):
                col_type = int
            elif token == 'event_time':
                col_type = str
            elif token == 'avg_threads':
                col_type = float
            elif cols:
                col = [c for c in source.available_columns if c[0] == cols[0]][0]
                col_type = col[1]
            else:
                col_type = str

            if col_type in (str, int, long):
                max_field_length = max([len(str(row[col_idx])) for row in dataset])
            elif col_idx == float:
                max_field_length = max([len(str(int(row[col_idx]))) for row in dataset]) + 3 # arbitrary!

            field_width = min(max_field_width, max(len(token), max_field_length))

            # left-align strings both in header and data
            if col_type == str:
                header_fmts.append('%%-%s.%ss' % (field_width, field_width))
            else:
                header_fmts.append('%%%s.%ss' % (field_width, field_width))
               
            if col_type == str:
                field_fmts.append('%%-%s.%ss' % (field_width, field_width))
            elif col_type in (int, long):
                field_fmts.append('%%%sd' % field_width)
            elif col_type == float:
                field_fmts.append('%%%s.%sf' % (field_width, 2)) # arbitrary

            total_field_width += field_width
            col_idx += 1

    report_width = total_field_width + (3 * (len(header_fmts) -1)) + 2
    hr = '-' * report_width
    title_pad = report_width - len(report.name) - 2
    title = '=== ' + report.name + ' ' + '=' * (title_pad - 3)
    header_fmt = ' ' + ' | '.join(header_fmts) + ' '
    field_fmt = ' ' + ' | '.join(field_fmts) + ' '

    print
    print title
    print 
    if dataset:
        print header_fmt % tuple([c[3] for c in report.full_projection()])
        print hr
        for row in dataset:
            print field_fmt % row
    else:
        print 'query returned no rows'
    print
    print



class Report:
    def __init__(self, name, projection, dimensions=[], where=[], order=[], output_fn=output_table_report):
        def reify_column_token(col_token):
            if col_token == 'samples':
                return (None, [], 'COUNT(1)', col_token)
            elif col_token == 'avg_threads':
                return (None, [], 'CAST(COUNT(1) AS REAL) / %(num_sample_events)s', col_token)
            elif col_token in ('pid', 'task', 'event_time'):
                return ('first_source', [col_token], col_token, col_token)

            for t in proc.all_sources:
                for c in t.schema_columns:
                    if col_token.lower() == c[0].lower():
                        return (t, [c[0]], c[0], c[0])

            raise Exception('projection/dimension column %s not found' % col_token)

        def process_filter_sql(filter_sql):
            idle_filter = "stat.state_id IN ('S', 'Z', 'I')"

            if filter_sql == 'active':
                return (proc.stat, ['state_id'], 'not(%s)' % idle_filter, filter_sql)
            elif filter_sql == 'idle':
                return (proc.stat, ['state_id'], idle_filter, filter_sql)
            else:
                raise Exception('arbitrary filtering not implemented')

        self.name = name
        self.projection = [reify_column_token(t) for t in projection if t]
        self.dimensions = [reify_column_token(t) for t in dimensions if t]
        self.order = [reify_column_token(t) for t in order if t]
        self.where = [process_filter_sql(t) for t in where if t]
        self.output_fn = output_fn

        # columns without a specific source are assigned the first source
        first_source = [c[0] for c in (self.projection + self.dimensions + self.order + self.where) if c[0] and c[0] != 'first_source'][0]
        self.projection = [(first_source if c[0] == 'first_source' else c[0], c[1], c[2], c[3]) for c in self.projection]
        self.dimensions = [(first_source if c[0] == 'first_source' else c[0], c[1], c[2], c[3]) for c in self.dimensions]
        self.order = [(first_source if c[0] == 'first_source' else c[0], c[1], c[2], c[3]) for c in self.order]
        self.where = [(first_source if c[0] == 'first_source' else c[0], c[1], c[2], c[3]) for c in self.where]

        self.sources = {} # source -> [cols]
        for d in [self.projection, self.dimensions, self.order, self.where]:
            for source, column_names, expr, token in d:
                source_columns = self.sources.get(source, ['pid', 'task', 'event_time'])
                source_columns.extend(column_names)
                self.sources[source] = source_columns
        if None in self.sources:
            del self.sources[None]


    def full_projection(self):
        return self.projection + [c for c in self.dimensions if c not in self.projection]


    def query(self):
        def render_col(c):
            return '%s.%s' % (c[0].name, c[2]) if c[0] else c[2]

        # build join conditions
        first_source_name = self.sources.keys()[0].name
        join_where = flatten([['%s.%s = %s.%s' % (s.name, c, first_source_name, c) for c in ['pid', 'task', 'event_time']] for s in self.sources.keys()[1:]])

        attr = {
            'projection': '\t' + ',\n\t'.join([render_col(c) for c in self.full_projection()]),
            'tables': '\t' + ',\n\t'.join([s.name for s in self.sources]),
            'where': '\t' + ' AND\n\t'.join([c[2] for c in self.where] + join_where),
            'dimensions': '\t' + ',\n\t'.join([render_col(c) for c in self.dimensions]),
            'order': '\t' + ',\n\t'.join([render_col(c) + ' DESC' for c in self.order]),
            'num_sample_events': '(SELECT COUNT(DISTINCT(event_time)) FROM %s)' % first_source_name
        }

        logging.debug('attr where=%s#end' % attr['where'])

        sql = 'SELECT\n%(projection)s\nFROM\n%(tables)s' % attr
        # tanel changed from self.where to attr['where']
        # TODO think through the logic of using self.where vs attr.where (in the context of allowing pid/tid to be not part of group by)
        if attr['where'].strip():
            sql += '\nWHERE\n%(where)s' % attr
        if attr['dimensions']:
            sql += '\nGROUP BY\n%(dimensions)s' % attr
        if attr['order']:
            sql += '\nORDER BY\n%(order)s' % attr

        # final substitution allows things like avg_threads to work
        return sql % attr


    def dataset(self, conn):
        logging.debug(self.query())
        r = conn.execute(self.query()).fetchall()
        logging.debug('Done')
        return r

    def output_report(self, conn):
        self.output_fn(self, self.dataset(conn))





