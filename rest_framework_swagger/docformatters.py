

class SimpleFormatter(object):
    def format(self, text):
        if not text:
            return None
        return text.replace('\n', '<br/>')


class MarkdownFormatter(object):
    def __init__(self):
        import markdown
        self.formatter = markdown.Markdown(extensions=['nl2br', 'def_list', 'sane_lists'], output_format='html5', safe_mode='escape')

    def format(self, text):
        if not text:
            return None
        if not isinstance(text, unicode):
            text = unicode(text, 'utf8')
        return self.formatter.convert(text)
