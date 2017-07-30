#!/usr/bin/env  python2
# coding=utf-8
from __future__ import absolute_import, division, print_function, unicode_literals

from calibre.utils.logging import ThreadSafeLog

AMAZONAPIQUICKVERSION = 1
from Queue import Queue
from calibre.utils.titlecase import titlecase
from StringIO import StringIO
import logging as python_logging
from threading import Event
from cgi import escape
import re, weakref, datetime
from urllib2 import urlopen
import traceback
from ast import literal_eval
from calibre.ebooks.metadata import check_isbn10, check_isbn13
from calibre.gui2.metadata.config import ConfigWidget
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source, Option
from logging import DEBUG, INFO, WARN, ERROR
from calibre_plugins.AmazonProductAdvertisingAPI.amazonsimpleproductapi import AmazonAPI, AmazonProduct, \
    AsinNotFoundException, LookupException, NoMorePagesException, RequestThrottledException, SearchException

try:
    # noinspection PyUnresolvedReferences
    from typing import Optional, unicode, Dict, List, NoReturn, Tuple, Any, AnyStr, Text
except ImportError:
    pass

__license__ = 'GPL v3'
__copyright__ = '2011, Kovid Goyal kovid@kovidgoyal.net'
__docformat__ = 'restructuredtext en'

class AmazonProductAdvertisingAPI(Source):
    amazonapi = None
    version = (0, 0, AMAZONAPIQUICKVERSION)
    minimum_calibre_version = (0, 8, 0)
    author = 'botmtl'
    name = 'AmazonProductAdvertisingAPI'
    supported_platforms = ['windows', 'osx', 'linux']

    #: Set of capabilities supported by this plugin.
    #: Useful capabilities are: 'identify', 'cover'
    capabilities = frozenset(['identify', 'cover'])

    #: List of metadata fields that can potentially be download by this plugin
    #: during the identify phase
    # identifier:amazon_DOMAIN will be added dynamically according to prefs
    touched_fields = frozenset(
        ['title', 'authors', 'identifier:isbn', 'comments', 'publisher', 'pubdate', 'series', 'tags'])

    #: Set this to True if your plugin returns HTML formatted comments
    has_html_comments = True

    #: Setting this to True means that the browser object will add
    #: Accept-Encoding: gzip to all requests. This can speedup downloads
    #: but make sure that the source actually supports gzip transfer encoding
    #: correctly first
    supports_gzip_transfer_encoding = False

    #: Set this to True to ignore HTTPS certificate errors when connecting
    #: to this source.
    ignore_ssl_errors = False

    #: Cached cover URLs can sometimes be unreliable (i.e. the download could
    #: fail or the returned image could be bogus. If that is often the case
    #: with this source set to False
    cached_cover_url_is_reliable = True

    #: A string that is displayed at the top of the config widget for this
    #: plugin
    config_help_message = None

    #: If True this source can return multiple covers for a given query
    can_get_multiple_covers = False

    #: If set to True covers downloaded by this plugin are automatically trimmed.
    auto_trim_covers = False

    #: If set to True, and this source returns multiple results for a query,
    #: some of which have ISBNs and some of which do not, the results without
    #: ISBNs will be ignored
    prefer_results_with_isbn = False

    #: A list of :class:`Option` objects. They will be used to automatically
    #: construct the configuration widget for this plugin
    options = [Option('AWS_ACCESS_KEY_ID', 'string', '', 'AWS_ACCESS_KEY_ID', 'AWS key'),
               Option('AWS_SECRET_ACCESS_KEY', 'string', '', 'AWS_SECRET_ACCESS_KEY', 'AWS secret'),
               Option('AWS_ASSOCIATE_TAG', 'string', '', 'AWS_ASSOCIATE_TAG', 'Amazon-associate username'),
               Option('domain', 'choices', 'US', 'Amazon Product API domain to use:',
                      'Metadata from BottlenoseAmazon will be fetched using this country\'s BottlenoseAmazon website.',
                      choices={'CA': 'ca', 'DE': 'de', 'ES': 'es', 'FR': 'fr', 'IN': 'in', 'IT': 'it', 'JP': 'co.jp',
                               'UK': 'co.uk', 'US': 'com', 'CN': 'cn'}),
               Option('extract_series_from_title', 'string',
                      '[r"\((?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\)", r"\[(?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\]"]',
                      'series extractor',
                      'a list of regular expression that be try successively to the title in an attempt to find the series_name and series_index. each regular expression must define group(series_name) and (series_index)'),
               Option('title_cleaner', 'string',
                      '''["re.sub(r'\[(.*?)\]', '', title, re.IGNORECASE)", "re.sub(r'\((.*?)\)','',title, flags=re.IGNORECASE)", "re.sub(r'[\:\,\-].*?( romance| novel| novella| story).*','',title, flags=re.IGNORECASE)"]''',
                      'Title cleaner:',
                      'A list of expressions to be evaluated. If (eval(<expression>) returns a value, title is set to this new value.'),
               Option('log_verbosity', 'choices', 'ERROR', 'log_verbosity', '',
                      choices={unicode(DEBUG): 'DEBUG', unicode(INFO): 'INFO', unicode(WARN): 'WARNING',
                               unicode(ERROR): 'ERROR'}),
               Option('reformat_author_initials', 'bool', True, 'reformat_author_initials', ''),
               Option('disable_title_author_search', 'bool', False, 'Disable title/author search:',
                      'Only books with identifiers will have a chance for to find a match with the metadata provider.')
               ]

    @property
    def touched_field(self):
        """
        Returns:
            unicode: the identifier that this plugin will return (amazon, amazon_it, amazon.co.uk)
        """
        return 'amazon' if self.prefs['domain'] == 'US' else 'amazon_' + self.prefs['domain']

    instances = []

    def __init__(self, *args, **kwargs):
        """

        Args:
            args:
            kwargs:
        """
        Source.__init__(self, *args, **kwargs)
        AmazonProductAdvertisingAPI.amazonapi = AmazonAPI(aws_key=self.prefs['AWS_ACCESS_KEY_ID'],
                                                          aws_secret=self.prefs['AWS_SECRET_ACCESS_KEY'],
                                                          aws_associate_tag=self.prefs['AWS_ASSOCIATE_TAG'],
                                                          Region=self.prefs['domain'], MaxQPS=0.2, Timeout=20)
        self.set_touched_fields()
        #self.stream = StringIO()
        #self.loghandler = python_logging.StreamHandler(self.stream)
        #self.logger = python_logging.getLogger('AmazonProductAdvertisingAPI')
        #self.logger.setLevel(python_logging.INFO)
        #for handler in self.logger.handlers:
        #    self.logger.removeHandler(handler)
        #self.logger.addHandler(self.loghandler)


    def is_configured(self):
        # type: () -> bool
        """
        :return: False if your plugin needs to be configured before it can be used. For example, it might need a username/password/API key.
        :rtype: bool
        """
        if self.prefs['AWS_ACCESS_KEY_ID'] and self.prefs['AWS_SECRET_ACCESS_KEY'] \
                and self.prefs['AWS_ASSOCIATE_TAG'] and self.prefs['extract_series_from_title'] \
                and self.prefs['title_cleaner']:
            return True

        return False

    def set_touched_fields(self):
        # type: () -> Any
        """
        Adds the amazon_id for the domain to the touched_fields
        """
        tf = [x for x in self.touched_fields]
        tf.append('identifier:' + self.touched_field)
        self.touched_fields = frozenset(tf)

    def save_settings(self, config_widget):
        # type: (ConfigWidget) -> Any
        """
        :param config_widget: ConfigWidget: Plugin configuration
        """

        Source.save_settings(self, config_widget)
        self.set_touched_fields()

    def get_cached_cover_url(self, identifiers):  # {{{
        # type: (Dict) -> [Text or None]
        """

        :param identifiers: Dict
        :return: AnyStr or None
        """
        cachedidentifier = identifiers.get(self.touched_field, None)
        if not cachedidentifier:
            cachedidentifier = identifiers.get('isbn', None)
            if not cachedidentifier:
                self.logger.error('No cached identifier!')
                return None

        cover_url = self.cached_identifier_to_cover_url(cachedidentifier)
        return cover_url

    def cli_main(self, args):
        # type: (List[AnyStr]) -> Any
        """
        This method is the main entry point for your plugins command line
        interface. It is called when the user does: calibre-debug -r "Plugin
        Name". Any arguments passed are present in the args variable.
        """

        # rows = self.gui.library_view.selectionModel().selectedRows()


        # rows = self.gui.library_view.selectionModel().selectedRows()
        # if not rows or len(rows) == 0:
        #    return error_dialog(self.gui, _('Cannot download metadata'), _('No books selected'), show=True)
        # db = self.gui.library_view.model().db
        # ids = [db.id(row.row()) for row in rows]
        # from calibre.gui2.metadata.bulk_download import Job
        # from calibre.gui2.metadata.bulk_download import start_download
        # from calibre.ebooks.metadata.sources.update import update_sources
        # tf = PersistentTemporaryFile('_metadata_bulk.logger')
        # update_sources()

        # from calibre.ebooks.metadata.opf2 import metadata_to_opf
        # noinspection PyUnresolvedReferences
        # from PyQt5.Qt import QObject, Qt, pyqtSignal
        # from calibre.gui2.ui import Main
        # noinspection PyUnresolvedReferences
        # job = ThreadedJob()
        # job.metadata_and_covers = (d.identify, d.covers)
        # job.download_debug_log = tf.name

        # job_manager.run_threaded_job(job)

        #
        # import os
        # identifier_type = args[1]
        # identifiers = str.split(args[2])
        # bulkmi = self.bulk_identify(identifier_type, identifiers)
        # for mi in bulkmi:
        #    f=open(os.environ.get('TEMP') + os.path.sep + mi.identifiers.get('identifier_type') + '.mi', 'rw')
        #    #f.write(metadata_to_opf(mi, default_lang='und'))
        #    f.close()
        # return
        pass

    # Metadata API {{{
    def get_book_url(self, identifiers):
        # type: (Dict) -> (Tuple[Text,Text,Text] or None)
        """
        Return a 3-tuple or None. The 3-tuple is of the form:
        (identifier_type, identifier_value, URL).
        The URL is the URL for the book identified by identifiers at this
        source. identifier_type, identifier_value specify the identifier
        corresponding to the URL.
        This URL must be browseable to by a human using a browser. It is meant
        to provide a clickable link for the user to easily visit the books page
        at this source.
        If no URL is found, return None. This method must be quick, and
        consistent, so only implement it if it is possible to construct the URL
        from a known scheme given identifiers.
        """
        identitifier_type = self.prefs['touched_field']
        identifier_value = identifiers.get(identitifier_type, None)
        return identitifier_type, identifier_value, 'https://www.amazon.%s/dp/%s' % (
        self.prefs['domain'], identifier_value)

    # noinspection PyDefaultArgument
    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        # type: (ThreadSafeLog, Queue, Event, Text, Optional[List[Text]], Optional[Dict], int) -> Optional[Text]
        """
        Identify a book by its title/author/isbn/etc.
        If identifiers(s) are specified and no match is found and this metadata
        source does not store all related identifiers (for example, all ISBNs
        of a book), this method should retry with just the title and author
        (assuming they were specified).
        If this metadata source also provides covers, the URL to the cover
        should be cached so that a subsequent call to the get covers API with
        the same ISBN/special identifier does not need to get the cover URL
        again. Use the caching API for this.
        Every Metadata object put into result_queue by this method must have a
        `source_relevance` attribute that is an integer indicating the order in
        which the results were returned by the metadata source for this query.
        This integer will be used by :meth:`compare_identify_results`. If the
        order is unimportant, set it to zero for every result.
        Make sure that any cover/isbn mapping information is cached before the
        Metadata object is put into result_queue.


        :return: Nothing
        :rtype: object
        :param log:  A logger object, use it to output debugging information/errors
        :param result_queue: A result Queue, results should be put into it.
                            Each result is a Metadata object
        :type result_queue: Queue
        :param abort: If abort.is_set() returns True, abort further processing
                      and return as soon as possible
        :type abort: Event
        :param title: The title of the book, can be None
        :type title: AnyStr or None
        :param authors: A list of authors of the book, can be None
        :type authors: List[AnyStr]
        :param identifiers: A dictionary of other identifiers, most commonly
                            {'isbn':'1234...'}
        :type identifiers Dict or None
        :param timeout: Timeout in seconds, no network request should hang for
                        longer than timeout.
        :type timeout: int
        :return: None if no errors occurred, otherwise a unicode representation
                 of the error suitable for showing to the user
        """
        self.logger = log
        major, minor, rev = AmazonProductAdvertisingAPI.version
        self.logger.info('Major', major, ' Minor:', minor, ' Rev:', rev)
        response = []  # type: Dict[Text,Text]
        if not identifiers: identifiers = {}
        if not authors: authors = []

        # keep identifiers that can be of use
        usable_identifiers = {key: identifiers[key] for key in ('isbn', 'amazon') if identifiers.has_key(key)}
        self.logger.info(unicode(usable_identifiers))

        if usable_identifiers:
            self.logger.info('identifiers:', usable_identifiers)
        if authors:
            self.logger.info('authors:', authors)
        if title:
            self.logger.info('title:', title)

        # try to identify with identifiers
        if usable_identifiers:
            try:
                response = self.identify_with_identifiers(identifiers=identifiers, timeout=timeout)
            except (AsinNotFoundException, LookupException):
                self.logger.info('No book with this ASIN, asin is not valid, or query malformed.')
                usable_identifiers = {}
            except Exception:
                self.logger.exception()

        # try to identify with author/title (either identify with identifiers failed or we never had identifiers to begin with)
        if not usable_identifiers and title and not self.prefs['disable_title_author_search']:
            response = self.identify_with_title_and_authors(title=title, authors=authors, timeout=timeout)

        # lookup and search both can potentially return a list of AmazonProducts
        try:
            for r in response:
                if abort.is_set():
                    raise (Exception('ABORT!'))
                result_queue.put(self.AmazonProduct_to_Metadata(r))
                return None
        except Exception:
            self.logger.exception()

    def identify_with_title_and_authors(self, title, authors, timeout=30):
        # type: (Event, Text, List[Text], int) -> List[AmazonProduct]
        """
        :param abort: Event: abort
        :param title: AnyStr: title
        :param authors: List[AnyStr]: authors
        :param timeout: int: timeout
        :return: List[AmazonProduct]: matching books (AmazonProducts)
        """
        request = dict(ResponseGroup='AlternateVersions,BrowseNodes,EditorialReview,Images,ItemAttributes',
                       SearchIndex="Books", n=4, Region=self.prefs['domain'], MaxQPS=0.8, Timeout=timeout,
                       Title='to_be_replaced')

        title_tokens = self.get_title_tokens(title)
        if title_tokens:
            self.logger.info('titletokens:', title_tokens)
            request.update(dict(Title=title_tokens))

        if authors:
            author_tokens = self.get_author_tokens(authors)
            if author_tokens:
                self.logger.info('author_tokens:', author_tokens)
                request.update(dict(Author=author_tokens))

        try:
            return AmazonProductAdvertisingAPI.amazonapi.search_n(**request)

        except NoMorePagesException as e:
            self.logger.error("NoMorePagesException:" + e.message)
            return []
        except RequestThrottledException as e:
            self.logger.error("RequestThrottledException:" + e.message)
            return []
        except SearchException as e:
            self.logger.error("SearchException:" + e.message)
            return []
        except Exception:
            self.logger.exception()
            return []

    def identify_with_identifiers(self, identifiers, timeout=30):
        # type: (Dict, int) -> List[AmazonProduct]
        """
        :param timeout: int: timeout
        :param identifiers: Dict : identifiers
        """
        request = dict(ResponseGroup='AlternateVersions,BrowseNodes,EditorialReview,Images,ItemAttributes',
                       Region=self.prefs['domain'], MaxQPS=0.8, Timeout=timeout)
        self.logger.info('identify_with_identifiers:', identifiers)
        amazon_id = identifiers.get(self.touched_field, None)
        isbn = identifiers.get('isbn', None)
        if amazon_id:
            request.update(dict(ItemId=amazon_id, IdType="ASIN"))
        elif check_isbn13(isbn) or check_isbn10(isbn):
            request.update(dict(ItemId=isbn, IdType="ISBN", SearchIndex='Books'))
        elif isbn:
            request.update(dict(ItemId=isbn, IdType="EAN", SearchIndex='Books'))

        response = AmazonProductAdvertisingAPI.amazonapi.lookup(**request)
        try:
            asins = []
            for r in response:
                if not r.binding == 'Kindle Edition':
                    if r.alternate_versions:
                        asins = [a.get('asin') for a in r.alternate_versions if a.get('binding') == 'Kindle Edition']
                        self.logger.info('alternate version is aavailable wish ASIN:', asins)

            if asins:
                #should call identify_with_identifiers instead
                return AmazonProductAdvertisingAPI.amazonapi.lookup(
                    ResponseGroup='BrowseNodes,EditorialReview,Images,ItemAttributes',
                    Region=self.prefs['domain'], MaxQPS=0.8, Timeout=timeout, ItemId=asins[0], IdType="ASIN")
        except:
            pass
        return response

    def bulk_identify_isbn(self, abort, list_isbn, timeout=10):
        # type: (Event, List[Text], int) -> Any
        products = AmazonProductAdvertisingAPI.amazonapi.lookup(
            Region=self.prefs['domain'], MaxQPS=0.8, Timeout=timeout,
            Title='to_be_replaced', ResponseGroup='AlternateVersions,BrowseNodes,EditorialReview,Images,ItemAttributes',
            ItemId=','.join(list_isbn), IdType="ISBN", SearchIndex='Books')

        if abort.is_set():
            raise Exception('ABORT!')

        for p in products:
            print(p.to_string())

        return

    def get_author_tokens(self, authors, only_first_author=True):
        # type: (List[Text], bool) -> Text or None
        author_tokens = Source.get_author_tokens(self, authors, only_first_author)
        if author_tokens:
            return ' '.join(author_tokens)
        else:
            return None

    def get_title_tokens(self, title, strip_joiners=True, strip_subtitle=False):
        # type: (Text, bool, bool) -> Text
        title_tokens = Source.get_title_tokens(self, title, strip_joiners, strip_subtitle)
        from types import GeneratorType
        new_title = ''
        if isinstance(title_tokens, GeneratorType):
            for t in title_tokens:
                new_title += t + ' '
        return new_title or title_tokens

    def clean_title(self, title):
        # type: (Text) -> Text
        """
        :param title: Text: title
        :return: Text: cleaned-up title
        """
        try:
            for r in literal_eval(self.prefs['title_cleaner']):
                result = eval(r)
                if result:
                    title = result.strip()
        except Exception:
            self.logger.exception()

        return titlecase(title)

    def parseAuthors(self, product):
        # type: (AmazonProduct) -> List[Text]
        """
        """
        authors_we_found = []
        if len(product.authors) > 0:
            authors_we_found = product.authors
        else:
            if len(product.creators) > 0:
                creator_name, creator_role = product.creators[0]
                authors_we_found = [creator_name]

        # authors_we_look_for_squished = [re.sub('[^A-Za-z]', '', a).upper() for a in self.authors_we_look_for]
        # authors_we_found_squished = [re.sub('[^A-Za-z]', '', a).upper() for a in authors_we_found]

        # dict_authors_we_look_for = dict(zip(authors_we_look_for_squished, self.authors_we_look_for))
        # dict_authors_we_found = dict(zip(authors_we_found_squished, authors_we_found))
        # authors_as_originally_formatted=[dict_authors_we_look_for[a] if a in dict_authors_we_look_for.keys() else dict_authors_we_found[a] for a in dict_authors_we_found.keys()]
        # return authors_as_originally_formatted
        try:
            if self.prefs['reformat_author_initials']:
                authors_we_found = [re.sub(r'^([A-Z])([A-Z]) (.+)$', r'\1.\2. \3', a, flags=re.IGNORECASE) for a in
                                    authors_we_found]
                authors_we_found = [re.sub(r'^([A-Z]) (.+)$', r'\1. \2', a, flags=re.IGNORECASE) for a in
                                    authors_we_found]
        except Exception:
            self.logger.exception()

        return authors_we_found

    def AmazonProduct_to_Metadata(self, product):
        # type: (AmazonProduct) -> Metadata
        """
        Convert AmazonProduct to Metadata
        :param product: AmazonProduct: AmazonAPI.AmazonProduct
        :return: Metadata: Metadata
        """
        self.logger.info('title:' + product.title)
        mi = Metadata(self.clean_title(product.title), self.parseAuthors(product))
        mi.source_relevance = 0

        if product.large_image_url:
            try:
                self.logger.info('large_image_url:' + product.large_image_url)
                img = urlopen('https://images-na.ssl-images-amazon.com/images/I/513q1hNq9mL.jpg')
                if 'image' in img.headers['Content-Type']:
                    mi.cover_data = img.read()
            except Exception:
                self.logger.exception()

        if product.asin:  # not in [product.isbn, product.eisbn, product.ean]:
            self.logger.info('product.asin is:' + product.asin)
            mi.set_identifier(self.touched_field, product.asin)
            if mi.cover_data and product.large_image_url:
                self.logger.info('cache_identifier_to_cover_url:' + product.asin + ',' + product.large_image_url)
                self.cache_identifier_to_cover_url(product.asin, product.large_image_url)

        if product.isbn or product.eisbn or product.ean:
            self.logger.info('product.isbn is:' + (product.isbn or product.eisbn or product.ean))
            mi.set_identifier('isbn', (product.isbn or product.eisbn or product.ean))
            if mi.cover_data and product.large_image_url:
                self.logger.info('cache_identifier_to_cover_url:' + (
                    product.isbn or product.eisbn or product.ean) + ',' + product.large_image_url)
                self.cache_identifier_to_cover_url((product.isbn or product.eisbn or product.ean),
                                                   product.large_image_url)

        if product.publisher:
            self.logger.info('product.publisher is:', product.publisher)
            mi.publisher = product.publisher

        if len(list(product.languages)) > 0:
            self.logger.info('product.languages is:' , product.languages)
            mi.languages = list(product.languages)

        if product.publication_date:
            self.logger.info('product.publication_date is:', product.publication_date.strftime('%Y-%m-%d'))
            mi.pubdate = datetime.datetime.combine(product.publication_date, datetime.time.min)
        elif product.release_date:
            self.logger.info('product.release_date is:', product.release_date.strftime('%Y-%m-%d'))
            mi.pubdate = datetime.datetime.combine(product.release_date, datetime.time.min)

        if product.editorial_review:
            self.logger.info('product.editorial_review is:', product.editorial_review)
            mi.comments = product.editorial_review

        if len(product.browse_nodes) > 0:
            self.logger.info('dic comprehension, product.browse_nodes')
            mi.tags = [p.name.text for p in product.browse_nodes]
            self.logger.info('tags:', mi.tags)

        series_name, series_index = self.parse_series(product.title)
        if series_name and series_index:
            self.logger.info('series::', series_name, ' ', series_index)
            mi.series = series_name
            mi.series_index = series_index

        self.clean_downloaded_metadata(mi)
        return mi

    def parse_series(self, title):
        # type: (Text) -> Tuple[Text or None,int or None]
        """
        :param title: Text
        :return: (series_name, series_index) or (None, None)
        """
        try:
            self.logger.info('title:' + title)
            for r in literal_eval(self.prefs['extract_series_from_title']):
                self.logger.info('parse_series:' + escape(r, quote=False))
                matches = re.search(r, title, re.IGNORECASE)
                if matches and matches.group('series_name') and matches.group('series_index'):
                    series_name = matches.group('series_name')
                    series_index = int(matches.group('series_index'))
                    self.logger('Found series name:' + series_name + '.  Found series_index:' + unicode(series_index))
                    return series_name, series_index

        except Exception:
            self.logger.exception(traceback.format_exc())

        return None, None

    # noinspection PyDefaultArgument
    def download_cover(self, log, result_queue, abort, title=None, authors=[], identifiers={}, timeout=30,
                       get_best_cover=False):
        # type: (ThreadSafeLog, Queue, Event, Optional[Text], Optional[List], Optional[Dict], int, bool) -> object
        """
        Download a cover and put it into result_queue. The parameters all have
        the same meaning as for :meth:`identify`. Put (self, cover_data) into
        result_queue.

        This method should use cached cover URLs for efficiency whenever
        possible. When cached data is not present, most plugins simply call
        identify and use its results.

        If the parameter get_best_cover is True and this plugin can get
        multiple covers, it should only get the "best" one.
        :param log: ThreadSafeLog: logger
        :param result_queue: Queue: results
        :param abort: Event: if is_set,abort
        :param title: Optional[unicode]: title
        :param authors: Optional[List]: authors
        :param timeout: int: timeout
        :param get_best_cover: bool:cover
        :return:
        :type identifiers: Optional[Dict]: identifiers
        """
        self.logger = log
        cached_url = self.get_cached_cover_url(identifiers)
        if cached_url is None:
            self.logger.info('No cached cover found, running identify')
            try:
                rq = Queue()
                self.identify(self.logger, rq, abort, title, authors, identifiers)
                cached_url = self.get_cached_cover_url(identifiers)
                if cached_url is None:
                    self.logger.info('Download cover failed.')
                    return 'Download cover failed.  Could not identify.'
            except:
                return

        if abort.is_set():
            return

        br = self.browser
        self.logger.info('Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            self.logger.error('Failed to download cover from:', cached_url)
            return 'Failed to download cover from:%s' % cached_url
            # }}}


if __name__ == '__main__':  # tests {{{
    # To run these test use: calibre-debug
    # src/calibre/ebooks/metadata/sources/amazon.py
    from calibre.ebooks.metadata.sources.test import title_test, authors_test, comments_test, test_identify_plugin

    com_tests = [  # {{{

        (  # Kindle edition with series
            {'identifiers': {'amazon': 'B0085UEQDO'}}, [title_test('Three Parts Dead', exact=True)]),

        # (  # + in title and uses id="main-image" for cover
        #    {'identifiers': {'isbn': '1933988770'}},
        #    [title_test('C++ Concurrency in Action: Practical Multithreading'),
        #     authors_test(['Anthony Williams']),
        #     isbn_test('1933988770')]),

        (  # Different comments markup, using Book Description section
            {'identifiers': {'isbn': '0982514506'}},
            [title_test("Griffin's Destiny", exact=True),
             comments_test('Jelena'), comments_test('Ashinji')],),

        (  # # in title
            {'title': 'Expert C# 2008 Business Objects', 'authors': ['Lhotka']},
            [title_test('Expert C# 2008 Business Objects'), authors_test(['Rockford Lhotka'])]),

        (  # Sophisticated comment formatting
            {'identifiers': {'amazon': 'B0725WGPFF'}},
            [title_test('P.S. I Spook You', exact=True), authors_test(['S. E. Harmon'])])

    ]

    test_identify_plugin(AmazonProductAdvertisingAPI.name, com_tests)
