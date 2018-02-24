#!/usr/bin/env  python2
# coding=utf-8

"""
AmazonProductAdvertisingAPI help
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import os
import re
from Queue import Queue
from ast import literal_eval
from threading import Event

from calibre.constants import config_dir
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.opf import get_metadata
from calibre.ebooks.metadata.opf2 import metadata_to_opf
from calibre.ebooks.metadata.sources.base import Option, Source
from calibre.gui2.metadata.config import ConfigWidget
from calibre.utils.logging import Log, ThreadSafeLog
from calibre.utils.titlecase import titlecase

try:
    from calibre_plugins.AmazonProductAdvertisingAPI.amazonsimpleproductapi import AmazonAPI, AmazonProduct, AmazonException
except ImportError:
    try:
        # noinspection PyUnresolvedReferences
        from amazonsimpleproductapi import AmazonAPI, AmazonProduct, AmazonException
    except:
        raise ImportError("amazonsimpleproductapi is missing")

try:
    # noinspection PyUnresolvedReferences
    from typing import Optional, unicode, Dict, List, NoReturn, Tuple, Any, AnyStr, Text
except:
    pass

__license__=u'GPL v3'
__copyright__=u'2011, Kovid Goyal kovid@kovidgoyal.net'
__docformat__=u'restructuredtext en'

class AmazonProductAdvertisingAPI(Source):
    """
    Uses Amazon API to get metadata
    """
    version=(1, 0, 1)
    minimum_calibre_version=(0, 8, 0)
    author=u'botmtl'
    name=u'AmazonProductAdvertisingAPI'
    supported_platforms=[u'windows', u'osx', u'linux']

    #: Set of capabilities supported by this plugin.
    #: Useful capabilities are: u'identify', u'cover'
    capabilities=frozenset([u'identify', u'cover'])


    @property
    def touched_field(self):
        """
        Returns:
            unicode: the identifier that this plugin will return (amazon, amazon_it, amazon.co.uk)
        """
        return u'amazon' if self.prefs[u'DOMAIN'] == u'US' else u'amazon_' + self.prefs[u'DOMAIN']

    #: Set this to True if your plugin returns HTML formatted comments
    has_html_comments=True

    #: Setting this to True means that the browser object will add
    #: Accept-Encoding: gzip to all requests. This can speedup downloads
    #: but make sure that the source actually supports gzip transfer encoding
    #: correctly first
    supports_gzip_transfer_encoding=False

    #: Set this to True to ignore HTTPS certificate errors when connecting
    #: to this source.
    ignore_ssl_errors=False

    #: Cached cover URLs can sometimes be unreliable (i.e. the download could
    #: fail or the returned image could be bogus. If that is often the case
    #: with this source set to False
    cached_cover_url_is_reliable=True

    #: A string that is displayed at the top of the config widget for this
    #: plugin
    config_help_message=None

    #: If True this source can return multiple covers for a given query
    can_get_multiple_covers=False

    #: If set to True covers downloaded by this plugin are automatically trimmed.
    auto_trim_covers=False

    #: If set to True, and this source returns multiple results for a query,    #: some of which have ISBNs and some of which do not, the results without
    #: ISBNs will be ignored
    prefer_results_with_isbn=False
    # {u'CA': u'ca', u'DE': u'de', u'ES': u'es', u'FR': u'fr', u'IN': u'in', u'IT': u'it', u'JP': u'co.jp', u'UK': u'co.uk', u'US': u'com', u'CN': u'cn'}
    #: A list of :class:`Option` objects. They will be used to automatically
    #: construct the configuration widget for this plugin
    options=[Option(u'AWS_ACCESS_KEY_ID', type_=u'string', default=u'', label=u'AWS_ACCESS_KEY_ID', desc=u'AWS key'),
             Option(u'AWS_SECRET_ACCESS_KEY', type_=u'string', default=u'', label=u'AWS_SECRET_ACCESS_KEY', desc=u'AWS secret'),
             Option(u'AWS_ASSOCIATE_TAG', type_=u'string', default=u'', label=u'AWS_ASSOCIATE_TAG', desc=u'Amazon-associate username'),
             Option(u'TITLE_CLEANER', type_=u'string', default=u'', label=u'title cleaner', desc=u''),
             Option(u'DOMAIN', type_=u'choices', default=u'US', label=u'Amazon Product API domain to use:',
                    desc=u'Metadata from BottlenoseAmazon will be fetched using this country\'s BottlenoseAmazon website.', choices=AmazonAPI.AMAZON_DOMAINS),
             Option(u'EXTRACT_SERIES_FROM_TITLE', type_=u'string',
                    default=u'[ru"\((?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\)", ru"\[(?P<series_name>.+?)\s+(#|book)\s*(?P<series_index>\d+)\]"]',
                    label=u'series extractor',
                    desc=u'A list of regular expression that are tried successively to the title in an attempt to find the series_name and series_index. each regular expression must define group(series_name) and (series_index)'),
             Option(u'LOG_FILTER_LEVEL', type_=u'choices', default=u'ERROR', label=u'LOG_FILTER_LEVEL', desc=u'',
                    choices={Log.DEBUG: u'DEBUG', Log.INFO: u'INFO', Log.WARN: u'WARNING', Log.ERROR: u'ERROR'}),
             Option(u'REFORMAT_AUTHOR_INITIALS', type_=u'bool', default=True, label=u'REFORMAT_AUTHOR_INITIALS', desc=u'Quality Check plugin required.'),
             Option(u'DISABLE_TITLE_AUTHOR_SEARCH', type_=u'bool', default=False, label=u'Disable title/author search:',
                    desc=u'Only books with identifiers will have a chance for to find a match with the metadata provider.'),
             Option(u'DISABLE_API_CALLS', type_=u'bool', default=False, label=u'Disable api calls:', desc=u'BATCH UPDATE.'),
             Option(u'TAGS_TO_ADD', type_=u'string', default='amazonapi', label=u'TAGS_TO_ADD:', desc=u'A comma separated list of tags to add.'),
             Option(u'METADATA_CACHE_ACTIVE', type_=u'bool', default=True, label=u'Keep downloaded metadata?', desc=u''),
             Option(u'METADATA_CACHE_LOCATION', type_=u'string', default=os.path.join(config_dir, 'amazonmi'), label=u'Where to store the metadata files.',
                    desc=u'Where to store the metadata files.'),
             Option(u'SEARCH_INDEX', type_=u'string', default=u'KindleStore', label=u'Search Index (Books or KindleStore).', desc=u'Search index filter.')]

    def config_widget(self):
        from calibre.gui2.metadata.config import ConfigWidget
        return ConfigWidget(self)

    @property
    def prefs(self):
        if self._config_obj is None:
            from calibre.utils.config import JSONConfig
            self._config_obj = JSONConfig('metadata_sources/AmazonProductAdvertisingAPI')
        return self._config_obj

    def __init__(self, *args, **kwargs):
        """

        Args:
            args:
            kwargs:
        """
        Source.__init__(self, *args, **kwargs)

        self.amazonapi=AmazonAPI(aws_key=self.prefs[u'AWS_ACCESS_KEY_ID'], aws_secret=self.prefs[u'AWS_SECRET_ACCESS_KEY'], aws_associate_tag=self.prefs[u'AWS_ASSOCIATE_TAG'],
                                 Region=self.prefs[u'DOMAIN'], MaxQPS=0.8, Timeout=20)
        self.base_request={u'ResponseGroup': u'AlternateVersions,BrowseNodes,EditorialReview,Images,ItemAttributes', u'Region': self.prefs[
            u'DOMAIN'], u'MaxQPS'          : 0.2, u'Timeout': 30}
        #: List of metadata fields that can potentially be download by this plugin
        #: during the identify phase
        # identifier:amazon_DOMAIN will be added dynamically according to prefs
        touched_fields = frozenset(['title', 'authors', 'identifier:amazon', 'identifier:isbn', 'rating', 'comments', 'publisher', 'pubdate', 'tags', 'series', 'identifier:'+self.touched_field])

    def cli_main(self, args):
        # type: (List[AnyStr]) -> None
        """
        Batch processing of either ASINs or ISBNs.  
        It is called when the user does: calibre-debug -r "AmazonProductAdvertisingAPI". 
        Needs a batch.txt with ASINS or ISBNS
        :param args: a comma separated list of identifiers
        :return: 0
        """
        # noinspection PyAttributeOutsideInit
        self.log=Log()
        if os.path.isfile(os.path.join(self.prefs['METADATA_CACHE_LOCATION'], u'batch.txt')):
            f=open(os.path.join(self.prefs['METADATA_CACHE_LOCATION'], u'batch.txt'), 'r')
            content=f.read()
            f.close()
            identifiers=re.split(r'[,\s;]', content)
        elif args:
            identifiers=re.split(r'[,\s;]', args[1])
        else:
            self.log.info(u'batch.txt or comma separated list of identifiers')
            return

        identifiers_isbn=identifiers_asins=[]
        if identifiers:
            identifiers=map(unicode, identifiers)
            identifiers_isbn=[i for i in identifiers if re.match(r'[0-9X\-]+', i) is not None]
            identifiers_asins=[i for i in identifiers if 'B' in i]

        if len(identifiers_isbn) > 0:
            self.bulk_identify(identifiers, u'ISBN')
        if len(identifiers_asins) > 0:
            self.bulk_identify(identifiers, u'ASIN')

        return

    def write_it(self, product, file_name):
        """
        :param product:
        :param file_name:
        """
        # type: (AmazonProduct, unicode or str) -> None
        persistentMI=os.path.join(self.prefs['METADATA_CACHE_LOCATION'], file_name)
        if not os.path.isfile(persistentMI):
            self.log.info(u'create:', persistentMI)
            f=open(persistentMI, str('wb'))
            mi=self.AmazonProduct_to_Metadata(product)
            f.write(metadata_to_opf(mi, default_lang=u'und'))
            f.close()

    def bulk_identify(self, identifiers, id_type=u"ASIN"):
        """
        :param id_type:
        :param identifiers:list(unicode):list of identifiers
        :return:list(Metadata)
        """
        # type: (List[unicode]) -> List[Metadata]
        if not os.path.exists(self.prefs['METADATA_CACHE_LOCATION']):
            os.makedirs(self.prefs['METADATA_CACHE_LOCATION'])

        lists_identifiers=[identifiers[x:x + 10] for x in range(0, len(identifiers), 10)]
        self.log.info(u'lists_identifiers:', lists_identifiers)
        request=self.base_request.copy()

        for li in lists_identifiers:
            request.update({u'ItemId': u','.join(li), u'IdType': id_type})
            if id_type == "ISBN":
                request.update({u'SearchIndex': self.prefs['SEARCH_INDEX']})
            try:
                products=self.amazonapi.item_lookup(**request)
                self.log.info(u'found', len(products), u'results')
                for p in products:
                    if id_type == u'ISBN' and p.isbn:
                        self.write_it(p, unicode(p.isbn) + u'.mi')
                    elif p.asin:
                        self.write_it(p, unicode(p.asin) + u'.mi')
                    else:
                        self.log(u"JUST LOST A RESULT")
            except AmazonException as e:
                self.log.error("AmazonException. Code:", e.code, ' Message:', e.msg)

    def is_configured(self):
        # type: () -> bool
        """
        :return: False if your plugin needs to be configured before it can be used. For example, it might need a username/password/API key.
        :rtype: bool
        """
        if self.prefs[u'AWS_ACCESS_KEY_ID'] and self.prefs[u'AWS_SECRET_ACCESS_KEY'] and self.prefs[u'AWS_ASSOCIATE_TAG']:
            return True

        return False

    def save_settings(self, config_widget):
        # type: (ConfigWidget) -> None
        """
        :param config_widget: ConfigWidget: Plugin configuration
        """

        Source.save_settings(self, config_widget)

    def get_cached_cover_url(self, identifiers):  # {{{
        # type: (Dict) -> [Text or None]
        """

        :param identifiers: Dict
        :return: AnyStr or None
        """
        cachedidentifier=identifiers.get(self.touched_field, None)
        if not cachedidentifier:
            cachedidentifier=identifiers.get(u'isbn', None)
            if not cachedidentifier:
                self.log.error(u'No cached identifier!')
                return None

        cover_url=self.cached_identifier_to_cover_url(cachedidentifier)
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
    #         'com' if self.prefs[u'DOMAIN'] == 'US' else self.prefs[u'DOMAIN'], identifier_value)
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
        # noinspection PyAttributeOutsideInit
        self.log=log
        response=[]  # type: Dict[Text,Text]
        if not identifiers: identifiers={}
        if not authors: authors=[]

        # keep identifiers that can be of use
        if identifiers.get(self.touched_field) or identifiers.get('mobi-asin') or identifiers.get(u'isbn'):
            try:
                mi=self.get_cached_mi(identifier=identifiers.get(u'amazon')) or self.get_cached_mi(identifier=identifiers.get(u'isbn'))
                if mi:
                    self.log.info('Found cached identifier for:', identifiers.get(self.touched_field) or identifiers.get('mobi-asin') or identifiers.get(u'isbn'))
                    result_queue.put(mi)
                    return
                if not self.prefs[u'DISABLE_API_CALLS']:
                    response=self.identify_with_identifiers(identifiers)
                else:
                    return
            except AmazonException as e:
                self.log.error("AmazonException.Code:", e.code, ' Message:', e.msg)
            except Exception:
                self.log.exception()

        # try to identify with author/title (either identify with identifiers failed or we never had identifiers to begin with)
        if len(response) == 0 and title and not self.prefs[u'DISABLE_TITLE_AUTHOR_SEARCH']:
            response=self.identify_with_title_and_authors(title=title, authors=authors)

        # lookup and search both can potentially return a list of AmazonProducts
        try:
            for r in response:
                if abort.is_set():
                    return
                # noinspection PyTypeChecker
                result_queue.put(self.AmazonProduct_to_Metadata(r))
                return None
        except Exception:
            self.log.exception()

    def get_cached_mi(self, identifier):
        """
        :param identifier: unicode: identifier
        :return:
        """
        if not identifier: return None
        persistentMI=os.path.join(self.prefs['METADATA_CACHE_LOCATION'], identifier + '.mi')
        if os.path.isfile(persistentMI):
            mi=get_metadata(open(persistentMI))[0]
            return mi
        return None

    def identify_with_title_and_authors(self, title, authors):
        # type: (Text, List[Text]) -> List[AmazonProduct] or None
        """
        :param title: AnyStr: title
        :param authors: List[AnyStr]: authors
        :return: List[AmazonProduct]: matching books (AmazonProducts)
        """
        if self.prefs[u'DISABLE_TITLE_AUTHOR_SEARCH'] or not title:
            return None

        request=self.base_request.copy()
        request.update({u'SearchIndex': self.prefs['SEARCH_INDEX']})

        title_tokens=u' '.join(self.get_title_tokens(title))
        if title_tokens:
            request.update({u'Title': title_tokens})

        if authors:
            author_tokens=u' '.join(self.get_author_tokens(authors))
            if author_tokens:
                request.update({u'Author': unicode(author_tokens)})
                
        try:
            self.log.info('amazonapi:', request)
            return self.amazonapi.item_search(**request)

        except AmazonException as e:
            self.log.error(u'AmazonException:', e.code, e.msg)
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
        request=self.base_request.copy()
        asin=identifiers.get(self.touched_field) or identifiers.get(u'mobi-asin')
        isbn=identifiers.get(u'isbn')

        if asin:
            request.update({u'ItemId': asin})
        elif isbn:
            request.update({u'ItemId': isbn, u'IdType': u'ISBN', u'SearchIndex': self.prefs['SEARCH_INDEX']})
        else:
            return []
        self.log.info('Item Lookup:', request)
        response=self.amazonapi.item_lookup(**request)
        response_kindle=[r for r in response if r.binding == u'Kindle Edition']
        if response_kindle:
            return response_kindle

        avasin=None
        for r in response:
            for av in r.alternate_versions:
                if av.get(u'binding') == u'Kindle Edition':
                    avasin=av.get('asin')
                    break
            if avasin:
                break

        if avasin:
            try:
                response_av_Kindle=self.identify_with_identifiers({u'amazon': avasin})
                return [r for r in response_av_Kindle]
            except:
                return response
        return response

    def _clean_title(self, title):
        # type: (Text) -> Text
        """
        :param title: Text: title
        :return: Text: cleaned-up title
        """
        try:
            for r in literal_eval(self.prefs[u'TITLE_CLEANER']):
                result=eval(r)
                if result:
                    title=result.strip()
        except Exception:
            self.log.exception()

        return titlecase(title)

    def _parseAuthors(self, product):
        """

        :param product: AmazonProductAPI
        :return: cleaned authors
        """
        authors_we_found=[]
        if len(product.authors) > 0:
            authors_we_found=product.authors
        else:
            if len(product.creators) > 0:
                creator_name, creator_role=product.creators[0]
                authors_we_found=[creator_name]

        try:
            if self.prefs[u'REFORMAT_AUTHOR_INITIALS']:
                authors_we_found=[re.sub(ur'^([A-Z])([A-Z]) (.+)$', ur'\1.\2. \3', a, flags=re.IGNORECASE) for a in authors_we_found]
                authors_we_found=[re.sub(ur'^([A-Z]) (.+)$', ur'\1. \2', a, flags=re.IGNORECASE) for a in authors_we_found]
        except Exception:
            self.log.exception()

        try:
            from calibre.utils.config import JSONConfig
            plugin_prefs=JSONConfig('plugins/Quality Check')
            from calibre_plugins.quality_check.config import STORE_OPTIONS, KEY_AUTHOR_INITIALS_MODE, AUTHOR_INITIALS_MODES
            initials_mode=plugin_prefs[STORE_OPTIONS].get(KEY_AUTHOR_INITIALS_MODE, AUTHOR_INITIALS_MODES[0])
            from quality_check.helpers import get_formatted_author_initials
            authors_we_found=[get_formatted_author_initials(initials_mode, author) for author in authors_we_found]
        except:
            pass

        return authors_we_found

    def AmazonProduct_to_Metadata(self, product):
        # type: (AmazonProduct) -> Metadata
        """
        Convert AmazonProduct to Metadata
        :param product: AmazonProduct: AmazonAPI.AmazonProduct
        :return: Metadata: book Metadata
        """
        mi=Metadata(self._clean_title(product.title), self._parseAuthors(product))
        mi.source_relevance=0

        mi.set_identifier(self.touched_field, product.asin)
        # self.log.info(u'asin:', product.asin)
        isbn=product.ean or product.isbn or product.eisbn
        if isbn:
            try:
                if _ISBNConvert.isI10(isbn): isbn=_ISBNConvert.convert(isbn)
                mi.set_identifier(u'isbn', isbn)
            except:
                self.log.exception()

        if product.large_image_url:
            self.cache_identifier_to_cover_url(product.asin, product.large_image_url)

        if product.publisher:
            mi.publisher=product.publisher

        if len(list(product.languages)) > 0:
            mi.languages=list(product.languages)

        if product.publication_date:
            mi.pubdate=datetime.datetime.combine(product.publication_date, datetime.time.min)
        elif product.release_date:
            mi.pubdate=datetime.datetime.combine(product.release_date, datetime.time.min)

        if product.editorial_review:
            mi.comments=product.editorial_review

        tags=set(self.prefs['TAGS_TO_ADD'].split(','))
        if len(product.browse_nodes) > 0:
            tags.update([p.name.text.lower() for p in product.browse_nodes if p.name and p.name.text])

        mi.tags=[tag.lower() for tag in tags]

        series_name, series_index=self.parse_series(product.title)
        if series_name:
            mi.series=series_name
            if series_index:
                mi.series_index=series_index
            else:
                mi.series_index=0

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
            for r in literal_eval(self.prefs[u'EXTRACT_SERIES_FROM_TITLE']):
                matches=re.search(r, title, re.IGNORECASE)
                if matches and matches.group(u'series_name') and matches.group(u'series_index'):
                    series_name=matches.group(u'series_name')
                    series_index=int(matches.group(u'series_index'))
                    self.log(u'Found series name:' + series_name + u'.  Found series_index:' + unicode(series_index))
                    return series_name, series_index

        except Exception:
            self.log.exception()

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
        # noinspection PyAttributeOutsideInit
        self.log=log
        cached_url=self.get_cached_cover_url(identifiers)
        if cached_url is None:
            self.log.info(u'No cached cover found, running identify')
            try:
                self.identify(self.log, result_queue, abort, title, authors, identifiers)
                cached_url=self.get_cached_cover_url(identifiers)
                if cached_url is None:
                    return u'Download cover failed.  Could not identify.'
            except:
                return

        if abort.is_set():
            return

        br=self.browser
        self.log.info(u'Downloading cover from:', cached_url)
        try:
            cdata=br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            self.log.error(u'Failed to download cover from:', cached_url)
            return u'Failed to download cover from:%s' % cached_url  # }}}

class _ISBNConvert(object):

    @staticmethod
    def _isbn_strip(isbn):
        """Strip whitespace, hyphens, etc. from an ISBN number and return
    the result."""
        short=re.sub(r"\W", "", isbn)
        return re.sub(r"\D", "X", short)

    @staticmethod
    def convert(isbn):
        """Convert an ISBN-10 to ISBN-13 or vice-versa."""
        short=_ISBNConvert._isbn_strip(isbn)
        if not _ISBNConvert.isValid(short):
            raise Exception(u"Invalid ISBN")
        if len(short) == 10:
            stem="978" + short[:-1]
            return stem + _ISBNConvert._check(stem)
        else:
            if short[:3] == "978":
                stem=short[3:-1]
                return stem + _ISBNConvert._check(stem)
            else:
                raise Exception("ISBN not convertible")

    @staticmethod
    def isValid(isbn):
        """Check the validity of an ISBN. Works for either ISBN-10 or ISBN-13."""
        short=_ISBNConvert._isbn_strip(isbn)
        if len(short) == 10:
            return _ISBNConvert.isI10(short)
        elif len(short) == 13:
            return _ISBNConvert.isI13(short)
        else:
            return False

    @staticmethod
    def _check(stem):
        """Compute the check digit for the stem of an ISBN. Works with either
        the first 9 digits of an ISBN-10 or the first 12 digits of an ISBN-13."""
        short=_ISBNConvert._isbn_strip(stem)
        if len(short) == 9:
            return _ISBNConvert.checkI10(short)
        elif len(short) == 12:
            return _ISBNConvert._checkI13(short)
        else:
            return False

    @staticmethod
    def checkI10(stem):
        """Computes the ISBN-10 check digit based on the first 9 digits of a stripped ISBN-10 number."""
        chars=list(stem)
        sum_isbn=0
        digit=10
        for char in chars:
            sum_isbn+=digit * int(char)
            digit-=1
        check=11 - (sum_isbn % 11)
        if check == 10:
            return "X"
        elif check == 11:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI10(isbn):
        """Checks the validity of an ISBN-10 number."""
        short=_ISBNConvert._isbn_strip(isbn)
        if len(short) != 10:
            return False
        chars=list(short)
        sum_isbn=0
        digit=10
        for char in chars:
            if char == 'X' or char == 'x':
                char="10"
            sum_isbn+=digit * int(char)
            digit-=1
        remainder=sum_isbn % 11
        if remainder == 0:
            return True
        else:
            return False

    @staticmethod
    def _checkI13(stem):
        """Compute the ISBN-13 check digit based on the first 12 digits of a stripped ISBN-13 number. """
        chars=list(stem)
        sumisbn=0
        count=0
        for char in chars:
            if count % 2 == 0:
                sumisbn+=int(char)
            else:
                sumisbn+=3 * int(char)
            count+=1
        check=10 - (sumisbn % 10)
        if check == 10:
            return "0"
        else:
            return str(check)

    @staticmethod
    def isI13(isbn):
        """Checks the validity of an ISBN-13 number."""
        short=_ISBNConvert._isbn_strip(isbn)
        if len(short) != 13:
            return False
        chars=list(short)
        sum_isbn=0
        count=0
        for char in chars:
            if count % 2 == 0:
                sum_isbn+=int(char)
            else:
                sum_isbn+=3 * int(char)
            count+=1
        remainder=sum_isbn % 10
        if remainder == 0:
            return True
        else:
            return False

if __name__ == u'__main__':  # tests {{{
    # To run these test use: calibre-debug
    # src/calibre/ebooks/metadata/sources/amazon.py
    from calibre.ebooks.metadata.sources.test import title_test, authors_test, test_identify_plugin

    com_tests=[  # {{{
        ({u'title': u'Expert C# 2008 Business Objects', u'authors': [u'Lhotka']}, [title_test(u'Expert C# 2008 Business Objects'), authors_test([u'Rockford Lhotka'])]),
        ({u'identifiers': {u'amazon': u'B0085UEQDO'}}, [title_test(u'Three Parts Dead', exact=True)]),
        ({u'identifiers': {u'isbn': u'0982514506'}}, [title_test(u'griffin\'s destiny', exact=True)]),
        ({u'identifiers': {u'amazon': u'B0725WGPFF'}}, [title_test(u'P.S. I Spook You', exact=True), authors_test([u'S. E. Harmon'])])]

    test_identify_plugin(AmazonProductAdvertisingAPI.name, com_tests)
