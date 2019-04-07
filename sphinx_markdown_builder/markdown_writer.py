import posixpath
from .doctree2md import Translator, Writer
from docutils import nodes
from pydash import _
import html2text

h = html2text.HTML2Text()


class PreMan:
    '''
    Utility class for managing quote/unquote operations. This is primarily
    used to prevent accidentally leaving pre-mode when nesting, and also
    to escape formatting when in quoted mode.
    '''
    def __init__(self, translator):
        self._in_quotes = 0
        self.translator = translator

    def push(self):
        '''
        Push a quote, which will insert a quote if we're not in quoted mode,
        otherwise it'll just increase the counter of quote-nestings.
        '''
        if self._in_quotes == 0:
            self.translator.add('`')
        self._in_quotes += 1

    def pop(self):
        '''
        Pop one nesting from the quote-counter. If this was the last element in
        the stack, it'll insert a backtick to end pre-formatted mode.
        '''
        self._in_quotes -= 1
        if self._in_quotes == 0:
            self.translator.add('`')

    def escape(self, text: str):
        '''
        Append *text* to the document output. If we're currently in
        pre-formatted mode this'll wrap *text* in `` ` ``'s so the
        formatting is applied correctly.

        :param text str: The text to escape
        :returns: None
        '''
        if self._in_quotes:
            self.translator.add('`{}`'.format(text))
        else:
            self.translator.add(text)


def reformat_title(node: nodes.Text):
    '''
    Attempts to change the contents of *node* to move a potential 'module'
    to the beginning from the end. This fixes an issue with markdown,
    where for Python the links (`refuri`) do not match up with the
    automatically generated anchors from Markdown.

    In particular, the headings for a module will be:

    `mypackage.mymodule module`

    Which becomes the anchor `mypackagemymodule-module` while the generated
    link will target `module-mypackage.mymodule`. This is incorrect both with
    handling dots and the position of the `module`.

    This does half of the corrective tranformation, while visit_reference
    removes the dots in the url.

    :param node nodes.Text: The node to transform
    '''
    if isinstance(node.children[0], nodes.Text):
        textnode = node.children[0]
        if 'module' in textnode:
            cleaned = textnode.replace('module', '').strip()
            node.children[0] = nodes.Text('Module ' + cleaned)


class MarkdownTranslator(Translator):
    row_entries = []
    rows = []
    tables = []
    tbodys = []
    theads = []

    def __init__(self, document, builder=None):
        Translator.__init__(self, document, builder)
        self.builder = builder
        self.definining_class = None

        self._quotes = PreMan(self)

    @property
    def rows(self):
        rows = []
        if not len(self.tables):
            return rows
        for node in self.tables[len(self.tables) - 1].children:
            if isinstance(node, nodes.row):
                rows.append(node)
            else:
                for node in node.children:
                    if isinstance(node, nodes.row):
                        rows.append(node)
        return rows

    def visit_title(self, node):
        reformat_title(node)
        self.add((self.section_level) * '#' + ' ')

    def depart_title(self, node):
        super(MarkdownTranslator, self).depart_title(node)

    def visit_desc(self, node):
        self.add('<dl>')

    def depart_desc(self, node):
        self.add('</dl>\n\n')

    def visit_desc_annotation(self, node):
        # if not node.astext().startswith('static'):
        self._quotes.escape(' _')
        self.add(node.astext().strip())
        raise nodes.SkipChildren()
        # if '=' not in node.astext():
        #     raise nodes.SkipNode()

    def depart_desc_annotation(self, node):
        # annotation, e.g 'method', 'class'
        # self.add(node.astext().strip())
        self._quotes.escape('_ ')
        pass

    def visit_desc_addname(self, node):
        # module preroll for class/method
        self._quotes.push()

    def depart_desc_addname(self, node):
        # module preroll for class/method
        self._quotes.pop()

    def visit_desc_name(self, node):
        # name of the class/method
        self._quotes.escape('**')
        self._quotes.push()

    def depart_desc_name(self, node):
        self._quotes.pop()
        self._quotes.escape('**')
        # name of the class/method

    def visit_desc_content(self, node):
        # the description of the class/method
        self.add('<dd>\n\n')
        # if node.astext() == '':
        #     self.add('*no description*')

    def depart_desc_content(self, node):
        # the description of the class/method
        self.add('</dd>')
        self.add('\n\n\n')

    def visit_definition_list(self, node):
        self.add('<dl>\n')

    def depart_definition_list(self, node):
        self.add('</dl>\n\n')

    def visit_definition_list_item(self, node):
        pass

    def depart_definition_list_item(self, node):
        pass

    def visit_desc_signature(self, node):
        self.add('<dt>\n\n')
        if node.parent['objtype'] != 'describe' and node['ids'] and node['first']:
            self.add('<!--[%s]-->' % node['ids'][0])

    def visit_term(self, node):
        self.add('<dt>')

    def depart_term(self, node):
        self.add('</dt>')

    def visit_definition(self, node):
        self.add('</dt>')
        self.add('<dd>')
        self.add('\n\n')
        self.start_level('  ')

    def depart_definition(self, node):
        self.add('</dd>\n')
        self.finish_level()

    def _refuri2http(self, node):
        url = node.get('refuri')
        if not node.get('internal'):
            return url

        title = node.get('reftitle')
        if url is None:
            return '#' + title

        this_doc = self.builder.current_docname
        if url in (None, ''):  # Reference to this doc
            url = self.builder.get_target_uri(this_doc)

        else:  # URL is relative to the current docname.
            this_dir = posixpath.dirname(this_doc)
            if this_dir:
                url = posixpath.normpath('{}/{}'.format(this_dir, url))

        if 'refid' in node:
            url += '#' + node['refid']

        return url

    def visit_reference(self, node):
        # If no target possible, pass through.
        document = self._refuri2http(node)
        parts = document.split('#')
        if len(parts) > 1:
            parts[1] = parts[1].replace('.', '')
            document = '#'.join(parts)
        self.add('[{0}]({1})'.format(node.astext(), document))
        raise nodes.SkipNode

    def depart_desc_signature(self, node):
        if not node.get('is_multiline'):
            self.add('\n</dt>\n')

    def visit_desc_parameterlist(self, node):
        self._quotes.push()
        self.add('(')
        # method/class ctor param list

    def depart_desc_parameterlist(self, node):
        self.add(')')
        self._quotes.pop()
        # method/class ctor param list

    def visit_desc_parameter(self, node):
        # single method/class ctr param
        text = node.astext()
        self._quotes.escape('_')
        if ':' in text:
            name, typ = text.split(':')
            self.add(name.strip())
            self._quotes.escape('_')
            self.add(': ')
            self._quotes.escape('__')
            self.add(typ.strip())
            self._quotes.escape('__')
            if node.next_node(descend=False, siblings=True):
                self.add(", ")

            raise nodes.SkipNode

    def depart_desc_parameter(self, node):
        # single method/class ctr param
        # if there are additional params, include a comma
        self._quotes.escape('_')
        if node.next_node(descend=False, siblings=True):
            self.add(", ")

    def visit_desc_returns(self, node):
        self.add(' → ')
        self._quotes.escape('**')
        self._quotes.push()

    def depart_desc_returns(self, foo):
        self._quotes.pop()
        self._quotes.escape('**')

    def visit_caption(self, node):
        pass

    def depart_caption(self, node):
        self.add('\n')
        pass

    def visit_admonition(self, node):
        '''
        .. note::
           The support for admonitions across Markdown is very inconsistent.

        This function generates admonitions as a quoted block with a heading
        derived from the admonition name. This is likely not the best for every
        Markdown renderer. While for example GitHub does have some support, it
        looks very basic.
        '''
        if node.children:
            title = node.pop(0)
            self.start_level('> ')
            self.add('## ' + title.astext() + '  \n')

    def depart_admonition(self, node):
        if node.children:
            self.finish_level()

    # list of parameters/return values/exceptions
    #
    # field_list
    #   field
    #       field_name (e.g 'returns/parameters/raises')
    #
    def visit_description(self, node):
        self.add('<dd>\n\n')

    def depart_description(self, node):
        self.add('</dd>')

    def visit_field_body(self, node):
        self.add('<dd>\n\n')
        if not node.children:
            self.add(' ')

    def depart_field_body(self, node):
        self.add('</dd>')

    def visit_field_list(self, node):
        self.add('<dl>')
        pass

    def depart_field_list(self, node):
        self.add('</dl>\n\n')
        pass

    def visit_field(self, node):
        self.add("\n")

    def depart_field(self, node):
        self.add("\n")

    def visit_field_name(self, node):
        # field name, e.g 'returns', 'parameters'
        self.add('\n**<dt>')

    def depart_field_name(self, node):
        self.add('</dt>**\n')

    def visit_literal_strong(self, node):
        self.add("**")

    def depart_literal_strong(self, node):
        self.add("**")

    def visit_literal_emphasis(self, node):
        self.add("*")

    def depart_literal_emphasis(self, node):
        self.add("*")

    def visit_title_reference(self, node):
        pass

    def depart_title_reference(self, node):
        pass

    def visit_versionmodified(self, node):
        # deprecation and compatibility messages
        # type will hold something like 'deprecated'
        self.add("**%s:** " % node.attributes["type"].capitalize())

    def depart_versionmodified(self, node):
        # deprecation and compatibility messages
        pass

    def visit_warning(self, node):
        """
        Sphinx warning directive
        """
        self.add('**WARNING**: ')

    def depart_warning(self, node):
        """
        Sphinx warning directive
        """
        pass

    def visit_note(self, node):
        """
        Sphinx note directive
        """
        self.add('**NOTE**: ')

    def depart_note(self, node):
        """
        Sphinx note directive
        """
        pass

    def visit_rubric(self, node):
        """
        Sphinx Rubric, a heading without relation to the document sectioning
        http://docutils.sourceforge.net/docs/ref/rst/directives.html#rubric
        """
        self.add("### ")

    def depart_rubric(self, node):
        """
        Sphinx Rubric, a heading without relation to the document sectioning
        http://docutils.sourceforge.net/docs/ref/rst/directives.html#rubric
        """
        self.add("\n\n")

    def visit_image(self, node):
        """
        Image directive
        """
        uri = node.attributes['uri']
        doc_folder = os.path.dirname(self.builder.current_docname)
        if uri.startswith(doc_folder):
            # drop docname prefix
            uri = uri[len(doc_folder):]
            if uri.startswith("/"):
                uri = "." + uri
        self.add('\n\n![image](%s)\n\n' % uri)

    def depart_image(self, node):
        """
        Image directive
        """
        pass

    def visit_autosummary_table(self, node):
        """
        Sphinx autosummary
        See http://www.sphinx-doc.org/en/master/usage/extensions/autosummary.html
        """
        pass

    def depart_autosummary_table(self, node):
        """
        Sphinx autosummary
        See http://www.sphinx-doc.org/en/master/usage/extensions/autosummary.html
        """
        pass

    ################################################################################
    # tables
    #
    # docutils.nodes.table
    #     docutils.nodes.tgroup [cols=x]
    #       docutils.nodes.colspec
    #
    #       docutils.nodes.thead
    #         docutils.nodes.row
    #         docutils.nodes.entry
    #         docutils.nodes.entry
    #         docutils.nodes.entry
    #
    #       docutils.nodes.tbody
    #         docutils.nodes.row
    #         docutils.nodes.entry

    def visit_table(self, node):
        self.tables.append(node)

    def depart_table(self, node):
        self.tables.pop()

    def visit_tabular_col_spec(self, node):
        pass

    def depart_tabular_col_spec(self, node):
        pass

    def visit_colspec(self, node):
        pass

    def depart_colspec(self, node):
        pass

    def visit_tgroup(self, node):
        pass

    def depart_tgroup(self, node):
        pass

    def visit_thead(self, node):
        if not len(self.tables):
            raise nodes.SkipNode
        self.theads.append(node)

    def depart_thead(self, node):
        for i in range(len(self.row_entries)):
            length = 0
            for row in self.rows:
                if len(row.children) > i:
                    entry_length = len(row.children[i].astext())
                    if entry_length > length:
                        length = entry_length
            self.add('| ' + ''.join(_.map(range(length), lambda: '-')) + ' ')
        self.add('|\n')
        self.row_entries = []
        self.theads.pop()

    def visit_tbody(self, node):
        if not len(self.tables):
            raise nodes.SkipNode
        self.tbodys.append(node)

    def depart_tbody(self, node):
        self.tbodys.pop()

    def visit_row(self, node):
        if not len(self.theads) and not len(self.tbodys):
            raise nodes.SkipNode
        self.rows.append(node)

    def depart_row(self, node):
        self.add('|\n')
        if not len(self.theads):
            self.row_entries = []
        try:
            self.rows.pop()
        except IndexError:
            pass

    def visit_entry(self, node):
        if not len(self.rows):
            raise nodes.SkipNode
        self.row_entries.append(node)
        self.add('| ')

    def depart_entry(self, node):
        length = 0
        i = len(self.row_entries) - 1
        for row in self.rows:
            if len(row.children) > i:
                entry_length = len(row.children[i].astext())
                if entry_length > length:
                    length = entry_length
        padding = ''.join(_.map(range(length - len(node.astext())), lambda: ' '))
        self.add(padding + ' ')

    def visit_strong(self, node):
        self.add('<b>')

    def depart_strong(self, node):
        self.add('</b>')


class MarkdownWriter(Writer):
    translator_class = MarkdownTranslator
