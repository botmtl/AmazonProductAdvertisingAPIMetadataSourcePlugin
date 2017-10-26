#!/usr/bin/env  python2
# coding=utf-8

"""
AmazonProductAdvertisingAPI help
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import os
import re
import traceback
from Queue import Queue
from ast import literal_eval
from calibre.utils.logging import Log
from threading import Event
from .isbn import isI10, convert, isI13
from calibre.constants import config_dir
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.opf2 import metadata_to_opf
from calibre.ebooks.metadata.sources.base import Option, Source
from calibre.gui2.metadata.config import ConfigWidget
from calibre.utils.logging import ThreadSafeLog
from calibre.utils.titlecase import titlecase
from calibre.ebooks.metadata.opf import get_metadata
# try:
from .amazonsimpleproductapi import AmazonAPI, AmazonProduct, AsinNotFoundException, LookupException, NoMorePagesException, RequestThrottledException, SearchException

# except ImportError:
# noinspection PyUnresolvedReferences
# from amazonsimpleproductapi import AmazonAPI, AmazonProduct, AsinNotFoundException, LookupException, NoMorePagesException, RequestThrottledException, SearchException

try:
    # noinspection PyUnresolvedReferences
    from typing import Optional, unicode, Dict, List, NoReturn, Tuple, Any, AnyStr, Text
except ImportError:
    pass

__license__ = u'GPL v3'
__copyright__ = u'2011, Kovid Goyal kovid@kovidgoyal.net'
__docformat__ = u'restructuredtext en'

class AmazonProductAdvertisingAPI(Source):
    """
    Uses Amazon API to get metadata
    """
    version = (1, 0, 0)
    minimum_calibre_version = (0, 8, 0)
    author = u'botmtl'
    name = u'AmazonProductAdvertisingAPI'
    supported_platforms = [u'windows', u'osx', u'linux']

    #: Set of capabilities supported by this plugin.
    #: Useful capabilities are: u'identify', u'cover'
    capabilities = frozenset([u'identify', u'cover'])

    #: List of metadata fields that can potentially be download by this plugin
    #: during the identify phase
    # identifier:amazon_DOMAIN will be added dynamically according to prefs
    touched_fields = frozenset([u'title', u'authors', u'identifier:isbn', u'comments', u'publisher', u'pubdate', u'tags'])

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
    # {u'CA': u'ca', u'DE': u'de', u'ES': u'es', u'FR': u'fr', u'IN': u'in', u'IT': u'it', u'JP': u'co.jp', u'UK': u'co.uk', u'US': u'com', u'CN': u'cn'}
    #: A list of :class:`Option` objects. They will be used to automatically
    #: construct the configuration widget for this plugin
    options = [Option(u'AWS_ACCESS_KEY_ID', u'string', u'', u'AWS_ACCESS_KEY_ID', u'AWS key'), Option(u'AWS_SECRET_ACCESS_KEY', u'string', u'', u'AWS_SECRET_ACCESS_KEY', u'AWS secret'),
               Option(u'AWS_ASSOCIATE_TAG', u'string', u'', u'AWS_ASSOCIATE_TAG', u'Amazon-associate username'), Option(u'title_cleaner', u'string', u'', u'title cleaner', u''),
               Option(u'domain', u'choices', u'US', u'Amazon Product API domain to use:', u'Metadata from BottlenoseAmazon will be fetched using this country\'s BottlenoseAmazon website.', choices=AmazonAPI.AMAZON_DOMAINS),
               Option(u'extract_series_from_title', u'string', u'[ru"\((?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\)", ru"\[(?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\]"]', u'series extractor',
                      u'a list of regular expression that be try successively to the title in an attempt to find the series_name and series_index. each regular expression must define group(series_name) and (series_index)'),
               Option(u'log_verbosity', u'choices', u'ERROR', u'log_verbosity', u'', choices={ Log.DEBUG: u'DEBUG', Log.INFO: u'INFO', Log.WARN: u'WARNING', Log.ERROR: u'ERROR'}),
               Option(u'reformat_author_initials', u'bool', True, u'reformat_author_initials', u''),
               Option(u'disable_title_author_search', u'bool', False, u'Disable title/author search:', u'Only books with identifiers will have a chance for to find a match with the metadata provider.'),
               Option(u'disable_api_calls', u'bool', False, u'Disable api calls:', u'BATCH UPDATE.')]

    @property
    def touched_field(self):
        """
        Returns:
            unicode: the identifier that this plugin will return (amazon, amazon_it, amazon.co.uk)
        """
        return u'amazon' if self.prefs[u'domain'] == u'US' else u'amazon_' + self.prefs[u'domain']

    def __init__(self, *args, **kwargs):
        """

        Args:
            args:
            kwargs:
        """
        Source.__init__(self, *args, **kwargs)
        self.amazonapi = AmazonAPI(aws_key=self.prefs[u'AWS_ACCESS_KEY_ID'], aws_secret=self.prefs[u'AWS_SECRET_ACCESS_KEY'], aws_associate_tag=self.prefs[u'AWS_ASSOCIATE_TAG'], Region=self.prefs[u'domain'], MaxQPS=0.2, Timeout=20)
        self.set_touched_fields()
        self.base_request = {u'ResponseGroup': u'AlternateVersions,BrowseNodes,EditorialReview,Images,ItemAttributes', u'Region': self.prefs[u'domain'], u'MaxQPS': 0.2, u'Timeout': 30}
        self.amazontempfolder = os.path.join(config_dir, 'amazonmi')

    def cli_main(self, args):
        # type: (List[AnyStr]) -> None
        """
        This method is the main entry point for your plugins command line
        interface. It is called when the user does: calibre-debug -r "Plugin
        Name". Any arguments passed are present in the args variable.
        """
        self.log = Log()
        identifiers = args[1].split(u',')
        self.log.info(u'indentifiers:', identifiers)
        self.bulk_identify(identifiers)
        return

    def write_opf(self, product):
        if not os.path.exists(self.amazontempfolder):
            os.makedirs(self.amazontempfolder)

        self.write_it(product.asin, product)
        if product.ean or product.isbn or product.eisbn:
            self.write_it(product.ean or product.isbn or product.eisbn, product)

    def write_it(self, id, product):
        self.log("write_it",id)
        persistentMI = os.path.join(self.amazontempfolder, id + u'.mi')
        self.log("write_it path", persistentMI)
        if not os.path.isfile(persistentMI):
            self.log.info(u'create', persistentMI)
            f = open(persistentMI, str('wb'))
            mi = self.AmazonProduct_to_Metadata(product)
            f.write(metadata_to_opf(mi, default_lang=u'und'))
            f.close()

    def bulk_identify(self, identifiers):
        """
        :param identifiers:list(unicode):list of identifiers
        :return:list(Metadata)
        """
        # type: (List[unicode]) -> List[Metadata]

        lists_identifiers = [identifiers[x:x + 10] for x in range(0, len(identifiers), 10)]
        self.log.info(u'lists_identifiers:', lists_identifiers)
        request = self.base_request.copy()

        for li in lists_identifiers:
            request.update({u'ItemId': u','.join(li), u'IdType':u'ISBN', 'SearchIndex':'Books'})
            try:
                products_asin = self.amazonapi.item_lookup(**request)
                self.log.info(u"found", len(products_asin), u"results")
                for p in products_asin:
                    self.write_opf(p)
            except (LookupException,AsinNotFoundException,Exception) as e:
                self.log.info(e.message)
                self.log.exception()
                pass

    def is_configured(self):
        # type: () -> bool
        """
        :return: False if your plugin needs to be configured before it can be used. For example, it might need a username/password/API key.
        :rtype: bool
        """
        if self.prefs[u'AWS_ACCESS_KEY_ID'] and self.prefs[u'AWS_SECRET_ACCESS_KEY'] and self.prefs[u'AWS_ASSOCIATE_TAG'] and self.prefs[u'extract_series_from_title'] and self.prefs[u'title_cleaner']:
            return True

        return False

    def set_touched_fields(self):
        # type: () -> None
        """
        Adds the amazon_id for the domain to the touched_fields
        """
        tf = [x for x in self.touched_fields]
        tf.append(u'identifier:' + self.touched_field)
        self.touched_fields = frozenset(tf)

    def save_settings(self, config_widget):
        # type: (ConfigWidget) -> None
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
            cachedidentifier = identifiers.get(u'isbn', None)
            if not cachedidentifier:
                self.log.error(u'No cached identifier!')
                return None

        cover_url = self.cached_identifier_to_cover_url(cachedidentifier)
        return cover_url


    # # Metadata API {{{
    # def get_book_url(self, identifiers):
    #     # type: (Dict) -> (Tuple[Text,Text,Text] or None)
    #     """
    #     Return a 3-tuple or None. The 3-tuple is of the form:
    #     (identifier_type, identifier_value, URL).
    #     The URL is the URL for the book identified by identifiers at this
    #     source. identifier_type, identifier_value specify the identifier
    #     corresponding to the URL.
    #     This URL must be browseable to by a human using a browser. It is meant
    #     to provide a clickable link for the user to easily visit the books page
    #     at this source.
    #     If no URL is found, return None. This method must be quick, and
    #     consistent, so only implement it if it is possible to construct the URL
    #     from a known scheme given identifiers.
    #     """
    #     identitifier_type = self.touched_field
    #     identifier_value = identifiers.get(identitifier_type)
    #     if not identitifier_type or not identifier_value:
    #         return None
    #     url = u'https://www.amazon.%s/dp/%s' % (
    #         'com' if self.prefs[u'domain'] == 'US' else self.prefs[u'domain'], identifier_value)
    #     print("url" + url)
    #     return identitifier_type, identifier_value, url

    # noinspection PyDefaultArgument
    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        # type: (ThreadSafeLog, Queue, Event, Text, list(Text), dict(Text), int) -> Text or None
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
        :param log:  A log object, use it to output debugging information/errors
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
                            {u'isbn':u'1234...'}
        :type identifiers Dict or None
        :param timeout: Timeout in seconds, no network request should hang for
                        longer than timeout.
        :type timeout: int
        :return: None if no errors occurred, otherwise a unicode representation
                 of the error suitable for showing to the user
        """
        self.log = log
        self.log.filter_level = self.prefs[u'log_verbosity']
        response = []  # type: Dict[Text,Text]
        if not identifiers: identifiers = {}
        if not authors: authors = []

        # keep identifiers that can be of use
        if identifiers.get(self.touched_field) or identifiers.get('mobi-asin') or identifiers.get(u'isbn'):
            try:
                mi = self.get_cached_mi(identifier=identifiers.get(u'amazon')) or self.get_cached_mi(identifier=identifiers.get(u'isbn'))
                if mi:
                    result_queue.put(mi)
                    return
                if not self.prefs[u'disable_api_calls']:
                    response = self.identify_with_identifiers(identifiers)
                else:
                    return
            except (AsinNotFoundException, LookupException):
                self.log.error("AsinNotFoundException or LookupException")
            except Exception:
                self.log.exception()

        # try to identify with author/title (either identify with identifiers failed or we never had identifiers to begin with)
        if len(response) == 0 and title and not self.prefs[u'disable_title_author_search']:
            response = self.identify_with_title_and_authors(title=title, authors=authors)

        # lookup and search both can potentially return a list of AmazonProducts
        try:
            for r in response:
                if abort.is_set():
                    raise (Exception(u'ABORT!'))
                result_queue.put(self.AmazonProduct_to_Metadata(r))
                return None
        except Exception:
            self.log.exception()

    def get_cached_mi(self, identifier):
        if not identifier: return None
        persistentMI = os.path.join(self.amazontempfolder, identifier + '.mi')
        if os.path.isfile(persistentMI):
            mi = get_metadata(open(persistentMI))[0]
            os.rename(persistentMI, persistentMI + '.bak2')
            return mi
        return None

    def identify_with_title_and_authors(self, title, authors):
        # type: (Text, List[Text]) -> List[AmazonProduct] or None
        """
        :param title: AnyStr: title
        :param authors: List[AnyStr]: authors
        :return: List[AmazonProduct]: matching books (AmazonProducts)
        """
        if self.prefs[u'disable_title_author_search'] or not title:
            return None

        request = self.base_request.copy()
        request.update({u'SearchIndex': u'Books'})

        title_tokens = u' '.join(self.get_title_tokens(title))
        if title_tokens:
            self.log.info(u'titletokens:', title_tokens)
            request.update({u'Title': title_tokens})

        if authors:
            author_tokens = u' '.join(self.get_author_tokens(authors))
            if author_tokens:
                self.log.info(u'author_tokens:', author_tokens)
                request.update({u'Author': unicode(author_tokens)})

        try:
            print(request)
            return self.amazonapi.item_search(**request)

        except NoMorePagesException as e:
            self.log.error(u'NoMorePagesException:', e.message)
            return []
        except RequestThrottledException as e:
            self.log.error(u'RequestThrottledException:', e.message)
            return []
        except SearchException as e:
            self.log.error(u'SearchException:', e.message)
            return []
        except Exception:
            self.log.exception()
            return []

    def identify_with_identifiers(self, identifiers):
        # type: (Dict) -> List[AmazonProduct] or None
        """
        :param identifiers: Dict : identifiers
        """
        self.log.info('identify_with_identifiers', identifiers)
        request = self.base_request.copy()
        asin = identifiers.get(self.touched_field) or identifiers.get(u'mobi-asin')
        isbn = identifiers.get(u'isbn')
        
        if asin:
            request.update({u'ItemId': asin})
        elif isbn:
            request.update({u'ItemId': isbn, u'IdType': u'ISBN', u'SearchIndex': u'Books'})
        else:
            return []
        self.log.info('Item Lookup:', request)
        response = self.amazonapi.item_lookup(**request)
        response_kindle = [r for r in response if r.binding == u'Kindle Edition']
        if response_kindle:
            return response_kindle

        avasin = None
        for r in response:
            for av in r.alternate_versions:
                if av.get(u'binding') == u'Kindle Edition':
                    avasin = av.get('asin')
                    break
            if avasin:
                break

        if avasin:
            try:
                response_av_Kindle = self.identify_with_identifiers({u'amazon': avasin})
                return [r for r in response_av_Kindle]
            except:
                return response
        return response



    def clean_title(self, title):
        # type: (Text) -> Text
        """
        :param title: Text: title
        :return: Text: cleaned-up title
        """
        try:
            for r in literal_eval(self.prefs[u'title_cleaner']):
                result = eval(r)
                if result:
                    title = result.strip()
        except Exception:
            self.log.exception()

        return titlecase(title)

    def parseAuthors(self, product):
        """

        :param product: AmazonProductAPI
        :return: cleaned authors
        """
        authors_we_found = []
        if len(product.authors) > 0:
            authors_we_found = product.authors
        else:
            if len(product.creators) > 0:
                creator_name, creator_role = product.creators[0]
                authors_we_found = [creator_name]

        try:
            if self.prefs[u'reformat_author_initials']:
                authors_we_found = [re.sub(ur'^([A-Z])([A-Z]) (.+)$', ur'\1.\2. \3', a, flags=re.IGNORECASE) for a in authors_we_found]
                authors_we_found = [re.sub(ur'^([A-Z]) (.+)$', ur'\1. \2', a, flags=re.IGNORECASE) for a in authors_we_found]
        except Exception:
            self.log.exception()

        try:
            from calibre.utils.config import JSONConfig
            plugin_prefs = JSONConfig('plugins/Quality Check')
            from calibre_plugins.quality_check.config import STORE_OPTIONS,KEY_AUTHOR_INITIALS_MODE,AUTHOR_INITIALS_MODES
            initials_mode = plugin_prefs[STORE_OPTIONS].get(KEY_AUTHOR_INITIALS_MODE, AUTHOR_INITIALS_MODES[0])
            from quality_check.helpers import get_formatted_author_initials
            authors_we_found = [get_formatted_author_initials(initials_mode,author) for author in authors_we_found]
        except:
            pass

        return authors_we_found

    def AmazonProduct_to_Metadata(self, product):
        # type: (AmazonProduct) -> Metadata
        """
        Convert AmazonProduct to Metadata
        :param product: AmazonProduct: AmazonAPI.AmazonProduct
        :return: Metadata: Metadata
        """
        mi = Metadata(self.clean_title(product.title), self.parseAuthors(product))
        mi.source_relevance = 0

        mi.set_identifier(self.touched_field, product.asin)
        self.log.info(u'asin:', product.asin)
        if product.ean or product.isbn or product.eisbn:
            mi.set_identifier(u'isbn', product.ean or product.isbn or product.eisbn)
            self.log.info(u'isbn:', product.ean or product.isbn or product.eisbn)

        if product.large_image_url:
            self.log.info(u'cache_identifier_to_cover_url:' + product.asin + u',' + product.large_image_url)
            self.cache_identifier_to_cover_url(product.asin, product.large_image_url)

        if product.publisher:
            self.log.info(u'product.publisher is:', product.publisher)
            mi.publisher = product.publisher

        if len(list(product.languages)) > 0:
            self.log.info(u'product.languages is:', product.languages)
            mi.languages = list(product.languages)

        if product.publication_date:
            self.log.info(u'product.publication_date is:', product.publication_date.strftime(u'%Y-%m-%d'))
            mi.pubdate = datetime.datetime.combine(product.publication_date, datetime.time.min)
        elif product.release_date:
            self.log.info(u'product.release_date is:', product.release_date.strftime(u'%Y-%m-%d'))
            mi.pubdate = datetime.datetime.combine(product.release_date, datetime.time.min)

        if product.editorial_review:
            self.log.info(u'product.editorial_review is:', product.editorial_review)
            mi.comments = product.editorial_review

        if len(product.browse_nodes) > 0:
            self.log.info(u'product.browse_nodes:', product.browse_nodes)
            mi.tags = [p.name.text for p in product.browse_nodes]
            mi.tags.extend(['AMAAPI'])
            self.log.info(u'tags:', mi.tags)

        series_name, series_index = self.parse_series(product.title)
        if series_name and series_index:
            self.log.info(u'series:', series_name, u' ', series_index)
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
            self.log.info(u'title:' + title)
            for r in literal_eval(self.prefs[u'extract_series_from_title']):
                matches = re.search(r, title, re.IGNORECASE)
                if matches and matches.group(u'series_name') and matches.group(u'series_index'):
                    series_name = matches.group(u'series_name')
                    series_index = int(matches.group(u'series_index'))
                    self.log(u'Found series name:' + series_name + u'.  Found series_index:' + unicode(series_index))
                    return series_name, series_index

        except Exception:
            self.log.exception(traceback.format_exc())

        return None, None

    # noinspection PyDefaultArgument
    def download_cover(self, log, result_queue, abort, title=None, authors=[], identifiers={}, timeout=30, get_best_cover=False):
        # type: (ThreadSafeLog, Queue, Event, Text, list(Text), dict(Text), int, bool) -> object
        """
        Download a cover and put it into result_queue. The parameters all have
        the same meaning as for :meth:`identify`. Put (self, cover_data) into
        result_queue.

        This method should use cached cover URLs for efficiency whenever
        possible. When cached data is not present, most plugins simply call
        identify and use its results.

        If the parameter get_best_cover is True and this plugin can get
        multiple covers, it should only get the best one.
        :param log: ThreadSafeLog: log
        :param result_queue: Queue: results
        :param abort: Event: if is_set,abort
        :param title: Optional[unicode]: title
        :param authors: Optional[List]: authors
        :param timeout: int: timeout
        :param get_best_cover: bool:cover
        :return:
        :type identifiers: Optional[Dict]: identifiers
        """
        self.log = log
        cached_url = self.get_cached_cover_url(identifiers)
        if cached_url is None:
            self.log.info(u'No cached cover found, running identify')
            try:
                rq = Queue()
                self.identify(self.log, rq, abort, title, authors, identifiers)
                cached_url = self.get_cached_cover_url(identifiers)
                if cached_url is None:
                    self.log.info(u'Download cover failed.')
                    return u'Download cover failed.  Could not identify.'
            except:
                return

        if abort.is_set():
            return

        br = self.browser
        self.log.info(u'Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            self.log.error(u'Failed to download cover from:', cached_url)
            return u'Failed to download cover from:%s' % cached_url  # }}}

if __name__ == u'__main__':  # tests {{{
    # To run these test use: calibre-debug
    # src/calibre/ebooks/metadata/sources/amazon.py
    from calibre.ebooks.metadata.sources.test import title_test, authors_test, test_identify_plugin

    com_tests = [  # {{{
        ({u'title': u'Expert C# 2008 Business Objects', u'authors': [u'Lhotka']}, [title_test(u'Expert C# 2008 Business Objects'), authors_test([u'Rockford Lhotka'])]),
        ({u'identifiers': {u'amazon': u'B0085UEQDO'}}, [title_test(u'Three Parts Dead', exact=True)]),
        ({u'identifiers': {u'isbn': u'0982514506'}}, [title_test(u'griffin\'s destiny: book three: the griffin\'s daughter trilogy', exact=True)]),
        ({u'identifiers': {u'amazon': u'B0725WGPFF'}}, [title_test(u'P.S. I Spook You', exact=True), authors_test([u'S. E. Harmon'])])]

    test_identify_plugin(AmazonProductAdvertisingAPI.name, com_tests)
