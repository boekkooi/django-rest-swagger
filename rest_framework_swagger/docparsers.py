import sys
from django.contrib.admindocs.utils import trim_docstring


class SimpleDocumentationParser(object):
    def parse(self, doc):
        rtn = {
            'query': None,
            'description': None,
            'summary': None,
        }
        if not doc or not isinstance(doc, str):
            return rtn

        rtn['description'] = self.strip_params_from_docstring(doc)
        rtn['summary'] = rtn['description'].split("\n")[0].split(".")[0]
        rtn['query'] = self._extract_query_params(doc)

        return rtn

    def _extract_query_params(self, doc):
        params = []
        split_lines = doc.split('\n')

        for line in split_lines:
            param = line.split(' -- ')
            if len(param) == 2:
                params.append({'paramType': 'query',
                               'name': param[0].strip(),
                               'description': param[1].strip(),
                               'dataType': ''})
        return params

    def strip_params_from_docstring(self, docstring):
        """
        Strips the params from the docstring (ie. myparam -- Some param) will
        not be removed from the text body
        """
        split_lines = trim_docstring(docstring).split('\n')

        cut_off = None
        for index, line in enumerate(split_lines):
            line = line.strip()
            if line.find('--') != -1:
                cut_off = index
                break
        if cut_off is not None:
            split_lines = split_lines[0:cut_off]

        return '\n'.join(split_lines).strip()


class RstLikeDocumentationParser(object):
    def parse(self, doc):
        rtn = {
            'query': None,
            'description': None,
            'summary': None,
        }
        if not doc or not isinstance(doc, str):
            return rtn

        rtn['description'] = []
        variable_names = ['deserializer', 'serializer']
        # TODO allow for types array or object (or similar) within the lists
        list_names = ['query', 'post']

        lines = doc.split('\n')

        collect_desc = True
        ignore_indent = sys.maxint
        item_list = item_list_indent = item_list_item = item_list_item_indent = False

        last_indent = -1
        last_indents = []
        for line in lines:
            if not line.strip():
                if item_list_indent is not False and item_list_item_indent is not False:
                    item_list_item['description'].append(line.strip())
                elif collect_desc:
                    rtn['description'].append(line.strip())
                continue

            # Check indent
            current_indent = len(line) - len(line.lstrip())
            if current_indent > last_indent:
                last_indents.append(last_indent)
            while current_indent < last_indent:
                last_indent = last_indents.pop()

            if item_list_indent >= current_indent:
                item_list = item_list_indent = False
            if item_list_item_indent >= current_indent:
                item_list_item = item_list_item_indent = False

            last_indent = current_indent

            # Ignore inner scope of other rst things
            if current_indent > ignore_indent:
                continue

            line = line.strip()

            # handle main sections/variables
            if item_list_indent is False:
                line_name, line_val = self._parse_variable(line)
                if line_name:
                    if line_name in variable_names:
                        rtn[line_name] = line_val
                        continue
                    if line_name in list_names:
                        item_list = []
                        rtn[line_name] = item_list
                        item_list_indent = current_indent
                        continue
                    ignore_indent = current_indent
                    collect_desc = False
                    continue

                if collect_desc:
                    rtn['description'].append(line.strip())
                continue

            # handle section parameters
            if item_list_item_indent is False:
                item_list_item_indent = current_indent

                item_list_item_name = line
                item_list_item_type = None
                type_index = line.find(':', 1)
                if type_index > 0:
                    item_list_item_name = line[:type_index].strip()
                    item_list_item_type = line[type_index+1:].strip()
                item_list_item = {
                    'name': item_list_item_name,
                    'type': item_list_item_type,
                    'description': []
                }
                item_list.append(item_list_item)
                continue

            # Check for param options
            line_name, line_val = self._parse_variable(line)
            if len(item_list_item['description']) == 0 and line_name:
                if line_name == 'required':
                    item_list_item['required'] = True
                if line_name == 'enum' and line_val:
                    item_list_item['enum'] = [x.strip() for x in line_val.split(',')]
                if line_name in ['minimum','maximum'] and line_val and line_val.isdigit():
                    item_list_item[line_name] = int(line_val)
                continue

            item_list_item['description'].append(line)

        return self._normalize(rtn, list_names)

    def _normalize(self, rtn, section_names):
        rtn['description'] = '\n'.join(rtn['description']).strip()
        for list_name in section_names:
            if list_name not in rtn or not rtn[list_name] or len(rtn[list_name]) == 0:
                continue

            for param in rtn[list_name]:
                param['description'] = '\n'.join(param['description']).strip()

        rtn['summary'] = rtn['description'].split("\n")[0].split(".")[0]

        if 'query' in rtn and rtn['query']:
            rtn['query'] = self._normalize_params(rtn['query'])
        if 'post' in rtn and rtn['post']:
            rtn['post'] = self._normalize_params(rtn['post'])
        return rtn

    def _parse_variable(self, line):
        """
        Extract a variable or section from a line.
        """
        if len(line) > 2 and line[0] is ':' and line.find(':', 2) > 1:
            val_idx = line.find(':', 2)
            name = line[1:val_idx].lower().strip()
            val = line[val_idx+1:].strip()

            return name, val or None
        return None, None

    def _normalize_params(self, params):
        for param in params:
            param['paramType'] = 'form'
            if ('type' not in param or not param['type']) and \
                ('dataType' not in param or not param['dataType']):
                param['type'] = param['dataType'] = ""
        return params